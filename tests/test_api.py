"""Local API (M7): a thin layer over core, local-only, with background jobs."""

import time

import pytest
from fastapi.testclient import TestClient
from test_code_joe import SCRIPTS, _gw, _paths, env, project  # noqa: F401

from ezra.api import create_app
from ezra.code_joe.agents import PLAN_SYSTEM
from ezra.store import Store

H = {"X-Ezra-Client": "test"}


@pytest.fixture
def client(env):  # noqa: F811
    store, envelope, tmp = env
    holder = {"scripts": SCRIPTS, "counts": {}}

    app = create_app(open_store=lambda: Store(tmp / "ezra.db"),
                     open_gateway=lambda s: _gw(s, holder["scripts"], counts=holder["counts"]),
                     run_kwargs=_paths(tmp), poll_seconds=0.01)
    return TestClient(app), envelope, holder


def wait(c, task_id, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = c.get(f"/api/jobs/{task_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job didn't finish")


def test_only_localhost_and_writes_need_the_client_header(client):
    c, envelope, _ = client
    assert c.get("/api/status", headers={"host": "evil.example"}).status_code == 403
    assert c.post(f"/api/tasks/{envelope.task_id}/run").status_code == 403  # no header
    assert c.get("/api/status").status_code == 200


def test_run_in_background_then_trace_and_list(client):
    c, envelope, _ = client
    r = c.post(f"/api/tasks/{envelope.task_id}/run", headers=H)
    assert r.status_code == 202 and r.json()["state"] == "running"
    job = wait(c, envelope.task_id)
    assert job == {**job, "state": "finished", "outcome": "passed"}
    t = c.get(f"/api/tasks/{envelope.task_id}").json()
    assert t["status"] == "done" and t["verdict"] == "PASS" and t["calls"] == 6
    steps = {row["step"] for row in t["rows"]}
    assert {"plan", "builder", "tester", "checks", "review", "deliver"} <= steps
    inv = next(row["invocation"] for row in t["rows"] if row["invocation"])
    assert c.get(f"/api/texts/{inv['response_hash']}").status_code == 200
    listed = c.get("/api/tasks").json()
    assert listed[0]["task_id"] == envelope.task_id and listed[0]["verdict"] == "PASS"
    assert listed[0]["spend_usd"] == pytest.approx(t["spend_usd"])
    # Running it again is refused up front, not as a failed job.
    assert c.post(f"/api/tasks/{envelope.task_id}/run", headers=H).status_code == 409


def test_hold_shows_in_the_inbox_and_is_answered_from_it(client):
    c, envelope, holder = client
    holder["counts"] = {PLAN_SYSTEM: 1_000_000}  # the plan call can't fit the $2 cap at all
    c.post(f"/api/tasks/{envelope.task_id}/run", headers=H)
    assert wait(c, envelope.task_id)["outcome"] == "held"
    inbox = c.get("/api/approvals").json()
    assert len(inbox) == 1 and inbox[0]["kind"] == "budget_hold"
    assert c.get("/api/status").json()["pending_approvals"] == 1
    holder["counts"] = {}
    r = c.post(f"/api/approvals/{inbox[0]['approval_id']}", headers=H,
               json={"approved": False})
    assert r.status_code == 202
    assert wait(c, envelope.task_id)["outcome"] == "stopped"
    assert c.get("/api/approvals").json() == []


def test_events_since_and_live_stream(client):
    c, envelope, _ = client
    c.post(f"/api/tasks/{envelope.task_id}/run", headers=H)
    wait(c, envelope.task_id)
    rows = c.get("/api/events", params={"task_id": envelope.task_id}).json()
    assert rows[0]["kind"] == "code_joe_started" and rows[-1]["kind"] == "delivered"
    later = c.get("/api/events", params={"after": rows[-2]["id"]}).json()
    assert [e["kind"] for e in later] == ["delivered"]
    with c.stream("GET", "/api/events/stream",
                  params={"after": rows[-2]["id"], "max_seconds": 0.2}) as s:
        body = "".join(s.iter_text())
    assert '"kind": "delivered"' in body and f"id: {rows[-1]['id']}" in body


def test_unknown_things_are_404(client):
    c, _, _ = client
    assert c.get("/api/tasks/task_nope").status_code == 404
    assert c.post("/api/approvals/apr_nope", headers=H, json={"approved": True}
                  ).status_code == 404


def test_agents_roster_reports_each_agent_with_its_numbers(client):
    c, envelope, _ = client
    c.post(f"/api/tasks/{envelope.task_id}/run", headers=H)
    wait(c, envelope.task_id)
    agents = {a["id"]: a for a in c.get("/api/agents").json()}
    assert list(agents) == ["intake", "code_joe", "builder", "tester", "guardian", "learner"]
    assert agents["code_joe"]["plans"] == 1 and agents["code_joe"]["calls"] == 1
    assert agents["builder"]["calls"] == 2 and agents["tester"]["runs"] == 1
    assert agents["guardian"]["verdicts"] == {"PASS": 1}
    plan = agents["code_joe"]["operations"][0]
    assert plan["model"] == "claude-opus-5-5" and plan["prompt_versions"][0].startswith(
        "code_joe.plan@")
    assert agents["intake"]["calls"] == 0 and agents["builder"]["cannot"]


def test_system_view_diff_and_run_cap(client):
    c, envelope, _ = client
    sysv = c.get("/api/system").json()
    assert {r["operation"] for r in sysv["routing"]} >= {"code_joe.plan", "guardian.tier2"}
    assert [r["rule"] for r in sysv["verdict_rules"]] == list(range(1, 10))
    assert sysv["limits"]["correction_cycle_limit"] == 1
    assert c.get(f"/api/tasks/{envelope.task_id}/diff").json()["diff"] == ""  # no branch yet
    # A run's cap can only go down.
    assert c.post(f"/api/tasks/{envelope.task_id}/run", headers=H,
                  json={"task_budget_usd": 5}).status_code == 400
    assert c.post(f"/api/tasks/{envelope.task_id}/run", headers=H,
                  json={"task_budget_usd": 1.5}).status_code == 202
    assert wait(c, envelope.task_id)["outcome"] == "passed"
    d = c.get(f"/api/tasks/{envelope.task_id}/diff").json()
    assert "+def double" in d["diff"] and "test_ac1_doubles_two" in d["diff"]


def test_learner_and_lessons_endpoints(client):
    c, envelope, _ = client
    agents = {a["id"]: a for a in c.get("/api/agents").json()}
    assert agents["learner"]["memory"] in ("off", "lessons", "frozen")
    assert c.get("/api/lessons").json() == []
    assert c.get("/api/lessons/les_nope").status_code == 404
    assert c.post("/api/lessons/les_nope/retire", headers=H).status_code == 409
    assert c.post(f"/api/tasks/{envelope.task_id}/run", headers=H,
                  json={"memory": "bogus"}).status_code == 400
    trace_names = {r["operation"] for r in c.get("/api/system").json()["routing"]}
    assert "learner.reflect" in trace_names


def test_agent_board_shows_each_agents_status_per_task(client):
    c, envelope, _ = client
    before = c.get("/api/agents/board").json()
    assert before["builder"][0]["state"] == "waiting"  # created, nobody has worked yet
    c.post(f"/api/tasks/{envelope.task_id}/run", headers=H)
    wait(c, envelope.task_id)
    board = c.get("/api/agents/board").json()
    row = {a: rows[0] for a, rows in board.items()}
    assert row["builder"]["state"] == "done" and row["builder"]["model"] == "claude-sonnet-5-5"
    assert row["guardian"]["last_kind"] == "delivered"
    assert row["learner"]["state"] in ("not_needed", "done")
