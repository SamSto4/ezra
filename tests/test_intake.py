"""Ezra intake: routing, criteria validation, one repair, task creation."""

import json

import pytest
from fakes import FakeClient, message

from ezra.config import load_limits, load_routing
from ezra.contracts import Severity, TaskStatus, Verification
from ezra.gateway import Gateway
from ezra.intake import SCHEMA, SYSTEM_PROMPT, IntakeError, Route, run_intake
from ezra.pricing import load_pricing
from ezra.store import Store


def crit(i, severity="critical", verification="test", check=None, text=None):
    return {"id": f"AC{i}", "text": text or f"behavior {i}", "severity": severity,
            "verification": verification, "check": check,
            "required_evidence": f"acceptance test for AC{i} passes"}


GOOD_CRITERIA = [crit(1), crit(2, "major"),
                 crit(3, "major", "deterministic", "tests_pass", "existing tests pass")]


def decision(route="code", **overrides):
    base = {"route": route, "answer": "", "task_title": "", "task_description": "",
            "acceptance_criteria": [], "constraints": [], "unsupported_reason": ""}
    if route == "code":
        base.update(task_title="Add sentence_count", acceptance_criteria=GOOD_CRITERIA,
                    task_description="Add sentence_count(text) to textkit.")
    if route == "direct":
        base["answer"] = "4"
    if route == "unsupported":
        base["unsupported_reason"] = "Ezra can't send email yet."
    base.update(overrides)
    return message(json.dumps(base), input_tokens=900, output_tokens=150)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "ezra.db")
    yield s
    s.close()


def intake(store, git_repo, replies, request="Add sentence_count"):
    client = FakeClient(replies)
    gw = Gateway(store=store, routing=load_routing(), limits=load_limits(),
                 pricing=load_pricing(), client=client)
    return run_intake(gw, request, project=git_repo, limits=load_limits()), client


def test_direct_answer(store, git_repo):
    result, _ = intake(store, git_repo, [decision("direct")], "what's 2+2")
    assert result.route is Route.DIRECT and result.answer == "4"
    assert result.envelope is None and store.get_task(result.request_id) is None


def test_unsupported(store, git_repo):
    result, _ = intake(store, git_repo, [decision("unsupported")], "email my team")
    assert result.route is Route.UNSUPPORTED and "email" in result.unsupported_reason


def test_code_request_creates_a_saved_task_with_typed_criteria(store, git_repo):
    result, _ = intake(store, git_repo, [decision()])
    env = result.envelope
    assert result.route is Route.CODE and env.task_id == result.request_id
    assert [c.id for c in env.acceptance_criteria] == ["AC1", "AC2", "AC3"]
    assert env.acceptance_criteria[0].severity is Severity.CRITICAL
    assert env.acceptance_criteria[2].verification is Verification.DETERMINISTIC
    assert env.project_ref == str(git_repo)
    assert env.counters.internal_iteration_cap == load_limits().internal_iteration_cap
    saved, status = store.get_task(env.task_id)
    assert saved == env and status is TaskStatus.CREATED
    # The intake call is billed to the task, so cost per task includes it.
    assert store.spend_for_task(env.task_id) == pytest.approx(
        result.invocations[0].actual_cost_usd)
    assert "intake_routed" in [e["kind"] for e in store.events_for_task(env.task_id)]


def test_request_uses_the_schema_and_keeps_the_system_prompt_static(store, git_repo):
    _, client = intake(store, git_repo, [decision()])
    sent = client.messages.stream_calls[0]
    assert sent["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert sent["system"][0]["text"] == SYSTEM_PROMPT  # cacheable: identical every call
    user = sent["messages"][0]["content"]
    assert "app.py" in user and "## Request" in user  # project summary goes after the cache


def test_invalid_criteria_get_one_repair(store, git_repo):
    bad = decision(acceptance_criteria=[crit(1), crit(2, "major", "deterministic", None)])
    result, client = intake(store, git_repo, [bad, decision()])
    assert result.route is Route.CODE and len(result.invocations) == 2
    repair = client.messages.stream_calls[1]["messages"]
    assert repair[1]["role"] == "assistant"
    assert "AC2" in repair[2]["content"] and "deterministic" in repair[2]["content"]
    kinds = [e["kind"] for e in store.events_for_task(result.request_id)]
    assert kinds.count("intake_invalid") == 1


@pytest.mark.parametrize("bad_criteria, expected", [
    ([crit(1, "major"), crit(2, "major")], "critical"),
    ([crit(1), crit(3)], "AC1, AC2"),
    ([crit(1)], "between 2"),
])
def test_rule_violations_are_named(store, git_repo, bad_criteria, expected):
    with pytest.raises(IntakeError) as err:
        intake(store, git_repo, [decision(acceptance_criteria=bad_criteria)] * 2)
    assert expected in str(err.value) and len(err.value.invocations) == 2


def test_no_task_is_saved_when_intake_fails(store, git_repo):
    with pytest.raises(IntakeError):
        intake(store, git_repo, [message("not json")] * 2)
    assert store.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_truncated_output_fails_without_repair(store, git_repo):
    with pytest.raises(IntakeError) as err:
        intake(store, git_repo, [message('{"route": "co', stop_reason="max_tokens")])
    assert "cut off" in str(err.value) and len(err.value.invocations) == 1


def test_direct_route_without_an_answer_is_repaired(store, git_repo):
    result, _ = intake(store, git_repo, [decision("direct", answer=""), decision("direct")])
    assert result.answer == "4" and len(result.invocations) == 2


def test_project_summary_handles_spaces_in_filenames(git_repo):
    import subprocess

    from ezra.intake import project_summary
    (git_repo / "with space.py").write_text("def f(a: int) -> int:\n    return a\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
    summary = project_summary(git_repo)
    assert "- with space.py" in summary and "def f(a: int) -> int" in summary


def test_missing_project_still_answers_questions(store, tmp_path):
    result, client = intake(store, tmp_path / "nowhere", [decision("direct")], "what's 2+2")
    assert result.answer == "4"
    assert "No project is available" in client.messages.stream_calls[0]["messages"][0]["content"]


def test_missing_project_blocks_code_tasks(store, tmp_path):
    with pytest.raises(IntakeError, match="no git project"):
        intake(store, tmp_path / "nowhere", [decision()])
    assert store.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_empty_reply_is_not_replayed(store, git_repo):
    with pytest.raises(IntakeError, match="no text") as err:
        intake(store, git_repo, [message("")])
    assert len(err.value.invocations) == 1
