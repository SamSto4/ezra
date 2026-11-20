"""Code Joe graph end to end with a scripted model: no network, real git, real pytest."""

import json
import subprocess

import pytest
from fakes import ScriptedClient, message, tool_turn

from ezra import core
from ezra.code_joe.agents import ADJUDICATE_SYSTEM, BUILD_SYSTEM, PLAN_SYSTEM, TEST_SYSTEM
from ezra.config import load_limits, load_routing
from ezra.contracts import (
    AcceptanceCriterion,
    ApprovalStatus,
    Budget,
    Department,
    DeterministicCheck,
    Severity,
    TaskEnvelope,
    TaskStatus,
    Verification,
)
from ezra.gateway import Gateway
from ezra.pricing import load_pricing
from ezra.store import Store

GOOD = "def double(x: int) -> int:\n    return x * 2\n"
WRONG = "def double(x: int) -> int:\n    return x * 3\n"
TESTS = ("from calc import double\n\n\ndef test_ac1_doubles_two():\n"
         "    assert double(2) == 4\n")
UNNAMED_TESTS = "from calc import double\n\n\ndef test_doubles():\n    assert double(2) == 4\n"


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "proj"
    (repo / "tests" / "acceptance").mkdir(parents=True)
    (repo / "tests" / "acceptance" / ".gitkeep").write_text("")
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["."]\ntestpaths = ["tests"]\n'
        "[tool.ruff]\nline-length = 100\n")
    (repo / "tests" / "test_existing.py").write_text("def test_existing():\n    assert True\n")
    for cmd in (["init", "-q"], ["add", "-A"],
                ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.fixture
def env(tmp_path, project):
    store = Store(tmp_path / "ezra.db")
    envelope = TaskEnvelope(
        target_department=Department.CODE_JOE, description="Add double(x) to calc.py",
        project_ref=str(project),
        acceptance_criteria=[
            AcceptanceCriterion(id="AC1", text="double(2) returns 4", severity=Severity.CRITICAL,
                                verification=Verification.TEST),
            AcceptanceCriterion(id="AC2", text="existing tests pass", severity=Severity.MAJOR,
                                verification=Verification.DETERMINISTIC,
                                check=DeterministicCheck.TESTS_PASS)],
        budget=Budget(task_limit_usd=2.0, daily_limit_usd=10.0))
    store.save_task(envelope)
    yield store, envelope, tmp_path
    store.close()


PLAN_JSON = json.dumps({
    "summary": "Add calc.py with double().", "steps": ["Create calc.py"],
    "interface": [{"path": "calc.py", "symbol": "double", "signature": "double(x: int) -> int",
                   "description": "Returns x times two."}],
    "test_file": "tests/acceptance/test_calc.py"})


def writes(path, content):
    return tool_turn(("write_file", {"path": path, "content": content}))


def run(store, tmp_path, scripts, task_id, **kwargs):
    gw = Gateway(store=store, routing=load_routing(), limits=load_limits(),
                 pricing=load_pricing(), client=ScriptedClient(scripts))
    return core.run_task(store, gw, task_id, checkpoint_path=tmp_path / "cp.db",
                         worktrees_dir=tmp_path / "wt", **kwargs), gw


def kinds(store, task_id):
    return [e["kind"] for e in store.events_for_task(task_id)]


def test_happy_path_ends_with_passing_tests_on_its_own_branch(env, project):
    store, envelope, tmp = env
    out, _ = run(store, tmp, {
        PLAN_SYSTEM: [message(PLAN_JSON, model="claude-opus-5-5")],
        BUILD_SYSTEM: [writes("calc.py", GOOD), message("Added double().")],
        TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("Tests added.")],
    }, envelope.task_id)
    assert out.outcome == "packaged" and out.status is TaskStatus.IN_REVIEW
    r = out.result
    assert r.status == "completed" and r.branch == f"ezra/{envelope.task_id}"
    assert sorted(r.changed_files) == ["calc.py", "tests/acceptance/test_calc.py"]
    pytest_run = next(c for c in r.command_runs if c.command == "pytest")
    assert pytest_run.exit_code == 0
    names = [c.name for c in pytest_run.cases]
    assert "tests/acceptance/test_calc.py::test_ac1_doubles_two" in names
    packaged = [e for e in store.events_for_task(envelope.task_id) if e["kind"] == "packaged"][0]
    assert packaged["criteria"] == {"AC1": "met", "AC2": "met"}
    # The work lives only on the task branch; the original checkout is untouched.
    assert not (project / "calc.py").exists()
    log = subprocess.run(["git", "log", "--oneline", r.branch], cwd=project,
                         capture_output=True, text=True).stdout
    assert "Code Joe" in log


def test_failed_check_is_adjudicated_and_fixed_once(env):
    store, envelope, tmp = env
    adjudication = json.dumps({"fault": "code", "reason": "double triples",
                               "builder_instructions": "Return x * 2.",
                               "tester_instructions": ""})
    out, gw = run(store, tmp, {
        PLAN_SYSTEM: [message(PLAN_JSON)],
        BUILD_SYSTEM: [writes("calc.py", WRONG), message("done"),
                       writes("calc.py", GOOD), message("fixed")],
        TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("done")],
        ADJUDICATE_SYSTEM: [message(adjudication)],
    }, envelope.task_id)
    assert out.outcome == "packaged" and out.result.status == "completed"
    assert kinds(store, envelope.task_id).count("checks_ran") == 2
    # Builder's fix turn got the failing test output.
    fix = [c for c in gw.client.messages.calls if c["system"][0]["text"] == BUILD_SYSTEM][2]
    assert "Return x * 2." in fix["messages"][0]["content"]
    assert "test_ac1_doubles_two" in fix["messages"][0]["content"]


def test_missing_test_ids_go_back_to_tester_without_a_model_judgment(env):
    store, envelope, tmp = env
    out, gw = run(store, tmp, {
        PLAN_SYSTEM: [message(PLAN_JSON)],
        BUILD_SYSTEM: [writes("calc.py", GOOD), message("done")],
        TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", UNNAMED_TESTS), message("done"),
                      writes("tests/acceptance/test_calc.py", TESTS), message("renamed")],
    }, envelope.task_id)
    assert out.result.status == "completed"
    adj = [e for e in store.events_for_task(envelope.task_id) if e["kind"] == "adjudicated"]
    assert adj[0]["by"] == "rule" and adj[0]["fault"] == "tests"
    assert not any(c["system"][0]["text"] == ADJUDICATE_SYSTEM for c in gw.client.messages.calls)


def test_still_failing_after_the_cap_is_packaged_as_partial(env):
    store, envelope, tmp = env
    code_fault = json.dumps({"fault": "code", "reason": "wrong", "builder_instructions": "fix",
                             "tester_instructions": ""})
    out, _ = run(store, tmp, {
        PLAN_SYSTEM: [message(PLAN_JSON)],
        BUILD_SYSTEM: [writes("calc.py", WRONG), message("a"),
                       writes("calc.py", WRONG), message("b"),
                       writes("calc.py", WRONG), message("c")],
        TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("t")],
        ADJUDICATE_SYSTEM: [message(code_fault), message(code_fault)],
    }, envelope.task_id)
    assert out.outcome == "packaged" and out.result.status == "partial"
    assert kinds(store, envelope.task_id).count("checks_ran") == 3  # 1 + the cap of 2
    assert "checks still failing after the iteration cap" in out.result.issues


def test_budget_hold_pauses_and_resumes_in_a_new_process(env, tmp_path):
    store, envelope, tmp = env
    scripts = {
        PLAN_SYSTEM: [message(PLAN_JSON)],
        BUILD_SYSTEM: [writes("calc.py", GOOD), message("done")],
        TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("done")],
    }
    # Plan's worst case (12k output tokens at the $25 fallback price) is about $0.30.
    out, _ = run(store, tmp, scripts, envelope.task_id, task_budget_usd=0.05)
    assert out.outcome == "held" and out.status is TaskStatus.HELD
    approval_id = out.holds[0]["approval_id"]
    assert [a.approval_id for a in store.pending_approvals()] == [approval_id]
    assert "model_call_started" not in kinds(store, envelope.task_id)  # nothing was sent

    # "New process": fresh store and gateway objects on the same files.
    store2 = Store(tmp / "ezra.db")
    gw2 = Gateway(store=store2, routing=load_routing(), limits=load_limits(),
                  pricing=load_pricing(), client=ScriptedClient(scripts))
    done = core.answer_hold(store2, gw2, approval_id, True, extend_usd=1.95,
                            checkpoint_path=tmp / "cp.db", worktrees_dir=tmp / "wt")
    assert done.outcome == "packaged" and done.result.status == "completed"
    assert store2.get_approval(approval_id).status is ApprovalStatus.APPROVED
    assert store2.pending_approvals() == []
    store2.close()


def test_rejected_hold_stops_the_task(env):
    store, envelope, tmp = env
    out, gw = run(store, tmp, {PLAN_SYSTEM: [message(PLAN_JSON)]}, envelope.task_id,
                  task_budget_usd=0.05)
    done = core.answer_hold(store, gw, out.holds[0]["approval_id"], False,
                            checkpoint_path=tmp / "cp.db", worktrees_dir=tmp / "wt")
    assert done.outcome == "stopped" and done.status is TaskStatus.FAILED
    assert "rejected" in done.stopped[0]


def test_only_created_tasks_run_and_budget_can_only_be_lowered(env):
    store, envelope, tmp = env
    with pytest.raises(core.RunError, match="lower"):
        run(store, tmp, {}, envelope.task_id, task_budget_usd=5.0)
    store.set_task_status(envelope.task_id, TaskStatus.DONE)
    with pytest.raises(core.RunError, match="only created"):
        run(store, tmp, {}, envelope.task_id)


def _gw(store, scripts, **kw):
    return Gateway(store=store, routing=load_routing(), limits=load_limits(),
                   pricing=load_pricing(), client=ScriptedClient(scripts, **kw))


def _paths(tmp):
    return {"checkpoint_path": tmp / "cp.db", "worktrees_dir": tmp / "wt"}


def _plan_hold(store, envelope, tmp, scripts):
    """Process 1: a big token count makes the plan call's worst case pass a $0.40 cap."""
    out = core.run_task(store, _gw(store, scripts, counts={PLAN_SYSTEM: 50_000}),
                        envelope.task_id, task_budget_usd=0.40, **_paths(tmp))
    assert out.outcome == "held" and out.holds[0]["node"] == "plan"
    return out.holds[0]["approval_id"]


SCRIPTS = {
    PLAN_SYSTEM: [message(PLAN_JSON)],
    BUILD_SYSTEM: [writes("calc.py", GOOD), message("done")],
    TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("done")],
}


def test_reject_applies_even_when_the_hold_does_not_recur(env):
    store, envelope, tmp = env
    aid = _plan_hold(store, envelope, tmp, SCRIPTS)
    # Process 2: small counts, so the plan call would now fit. The rejection must still stop it.
    gw2 = _gw(store, SCRIPTS)
    done = core.answer_hold(store, gw2, aid, False, **_paths(tmp))
    assert done.outcome == "stopped" and "rejected" in done.stopped[0]
    assert gw2.client.messages.calls == []  # no model call after a rejection


def test_approval_extension_applies_when_the_hold_does_not_recur(env):
    store, envelope, tmp = env
    aid = _plan_hold(store, envelope, tmp, SCRIPTS)
    gw2 = _gw(store, SCRIPTS)
    done = core.answer_hold(store, gw2, aid, True, extend_usd=0.5, **_paths(tmp))
    assert done.outcome == "packaged"
    app, conn = core._graph(store, gw2, tmp / "cp.db", tmp / "wt")
    values = app.get_state({"configurable": {"thread_id": envelope.task_id}}).values
    conn.close()
    assert values["budget_extra_task"] == pytest.approx(0.5)
    assert values["budget_extra_day"] == 0.0  # a task-budget HOLD never raises the daily cap
    assert store.get_approval(aid).details["extend_usd"] == 0.5


def test_both_workers_held_and_answered_one_at_a_time(env):
    store, envelope, tmp = env
    # Each worker alone is worth about $0.31, the plan about $0.30: under a $0.305 cap the
    # plan fits and both workers hold.
    counts = {BUILD_SYSTEM: 60_000, TEST_SYSTEM: 60_000}
    out = core.run_task(store, _gw(store, SCRIPTS, counts=counts), envelope.task_id,
                        task_budget_usd=0.305, **_paths(tmp))
    assert out.outcome == "held" and sorted(h["node"] for h in out.holds) == ["builder",
                                                                             "tester"]
    builder_hold = next(h for h in out.holds if h["node"] == "builder")["approval_id"]
    mid = core.answer_hold(store, _gw(store, SCRIPTS, counts=counts), builder_hold, True,
                           extend_usd=0.5, **_paths(tmp))
    assert mid.outcome == "held" and [h["node"] for h in mid.holds] == ["tester"]
    done = core.answer_hold(store, _gw(store, SCRIPTS, counts=counts),
                            mid.holds[0]["approval_id"], True, extend_usd=0.5, **_paths(tmp))
    assert done.outcome == "packaged" and done.result.status == "completed"
    assert store.pending_approvals() == []
