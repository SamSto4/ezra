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
from ezra.guardian.tier2 import SYSTEM as GUARDIAN_SYSTEM
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


def guardian(criteria=(), findings=(), corrections=(), summary="Looks right."):
    return message(json.dumps({
        "criteria": [{"criterion_id": c, "status": st, "evidence": "diff line 3"}
                     for c, st in criteria],
        "findings": [{"code": code, "severity": sev, "message": msg, "auto_fixable": True}
                     for code, sev, msg in findings],
        "required_corrections": list(corrections), "summary": summary}),
        model="claude-opus-5-5")


GUARDIAN_PASS = guardian()


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
        GUARDIAN_SYSTEM: [GUARDIAN_PASS],
    }, envelope.task_id)
    assert out.outcome == "passed" and out.status is TaskStatus.DONE
    assert out.review.verdict == "PASS" and out.review.matched_rule == 9 and out.reviews == 1
    r = out.result
    assert r.status == "completed" and r.branch == f"ezra/{envelope.task_id}"
    assert sorted(r.changed_files) == ["calc.py", "tests/acceptance/test_calc.py"]
    pytest_run = next(c for c in r.command_runs if c.command == "pytest")
    assert pytest_run.exit_code == 0
    names = [c.name for c in pytest_run.cases]
    assert "tests/acceptance/test_calc.py::test_ac1_doubles_two" in names
    reviewed = [e for e in store.events_for_task(envelope.task_id) if e["kind"] == "reviewed"][0]
    assert reviewed["criteria"] == {"AC1": "met", "AC2": "met"}
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
        GUARDIAN_SYSTEM: [GUARDIAN_PASS],
    }, envelope.task_id)
    assert out.outcome == "passed" and out.result.status == "completed"
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
        GUARDIAN_SYSTEM: [GUARDIAN_PASS],
    }, envelope.task_id)
    assert out.result.status == "completed"
    adj = [e for e in store.events_for_task(envelope.task_id) if e["kind"] == "adjudicated"]
    assert adj[0]["by"] == "rule" and adj[0]["fault"] == "tests"
    assert not any(c["system"][0]["text"] == ADJUDICATE_SYSTEM for c in gw.client.messages.calls)


def test_never_fixed_means_one_revise_then_escalate_never_a_third_attempt(env):
    store, envelope, tmp = env
    code_fault = json.dumps({"fault": "code", "reason": "wrong", "builder_instructions": "fix",
                             "tester_instructions": ""})
    out, gw = run(store, tmp, {
        PLAN_SYSTEM: [message(PLAN_JSON)],
        # 1 first run + 2 fix rounds, then 1 after REVISE + 1 fix round (cap 1 after REVISE)
        BUILD_SYSTEM: [m for i in range(5) for m in (writes("calc.py", WRONG), message(str(i)))],
        TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("t")],
        ADJUDICATE_SYSTEM: [message(code_fault), message(code_fault)],
    }, envelope.task_id)
    k = kinds(store, envelope.task_id)
    assert out.outcome == "escalated" and out.status is TaskStatus.ESCALATED
    assert out.reviews == 2 and k.count("revision_started") == 1
    assert out.review.verdict == "ESCALATE" and out.review.matched_rule == 4  # critical AC1
    assert k.count("checks_ran") == 5
    # Tier 1 settled both reviews: no Guardian model call, and Tester never reran.
    systems = [c["system"][0]["text"] for c in gw.client.messages.calls]
    assert GUARDIAN_SYSTEM not in systems and systems.count(TEST_SYSTEM) == 2  # 1 run, 2 turns
    # After the REVISE, failures went to Builder by rule (tests frozen), not to adjudication.
    assert systems.count(ADJUDICATE_SYSTEM) == 2


def test_budget_hold_pauses_and_resumes_in_a_new_process(env, tmp_path):
    store, envelope, tmp = env
    scripts = dict(SCRIPTS)
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
    assert done.outcome == "passed" and done.result.status == "completed"
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
    """Process 1: a big token count makes the plan call's worst case pass a $0.40 cap, and
    too big to shrink to fit (D-016): 60k input tokens alone take $0.375 of it."""
    out = core.run_task(store, _gw(store, scripts, counts={PLAN_SYSTEM: 60_000}),
                        envelope.task_id, task_budget_usd=0.40, **_paths(tmp))
    assert out.outcome == "held" and out.holds[0]["node"] == "plan"
    return out.holds[0]["approval_id"]


SCRIPTS = {
    PLAN_SYSTEM: [message(PLAN_JSON)],
    BUILD_SYSTEM: [writes("calc.py", GOOD), message("done")],
    TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("done")],
    GUARDIAN_SYSTEM: [GUARDIAN_PASS],
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
    assert done.outcome == "passed"
    app, conn = core._graph(store, gw2, tmp / "cp.db", tmp / "wt")
    values = app.get_state({"configurable": {"thread_id": envelope.task_id}}).values
    conn.close()
    assert values["budget_extra_task"] == pytest.approx(0.5)
    assert values["budget_extra_day"] == 0.0  # a task-budget HOLD never raises the daily cap
    assert store.get_approval(aid).details["extend_usd"] == 0.5


def test_both_workers_held_and_answered_one_at_a_time(env):
    store, envelope, tmp = env
    # The plan (~$0.30) fits a $0.305 cap. Each worker's 120k input tokens alone cost $0.30,
    # leaving too little output room to shrink into (D-016), so both hold.
    counts = {BUILD_SYSTEM: 120_000, TEST_SYSTEM: 120_000}
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
    assert done.outcome == "passed" and done.result.status == "completed"
    assert store.pending_approvals() == []


HARDCODED = "def double(x: int) -> int:\n    return {2: 4}.get(x, 0)\n"


def test_guardian_catches_special_casing_revise_once_then_pass(env):
    store, envelope, tmp = env
    flagged = guardian(findings=[("special_cases_test_inputs", "major",
                                  "double() looks up the test input instead of doubling.")],
                       corrections=["Implement double as x * 2 for every int."],
                       summary="Passes tests by special-casing.")
    out, gw = run(store, tmp, {
        PLAN_SYSTEM: [message(PLAN_JSON)],
        BUILD_SYSTEM: [writes("calc.py", HARDCODED), message("done"),
                       writes("calc.py", GOOD), message("fixed")],
        TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("done")],
        GUARDIAN_SYSTEM: [flagged, GUARDIAN_PASS],
    }, envelope.task_id)
    assert out.outcome == "passed" and out.reviews == 2
    first, second = store.reviews_for_task(envelope.task_id)
    assert (first.verdict, first.matched_rule, first.tier) == ("REVISE", 7, "tier2_checklist")
    assert first.required_corrections == ["Implement double as x * 2 for every int."]
    assert second.verdict == "PASS"
    calls = gw.client.messages.calls
    fix = [c for c in calls if c["system"][0]["text"] == BUILD_SYSTEM][2]
    assert "Implement double as x * 2" in fix["messages"][0]["content"]
    # Tests are frozen after REVISE: Tester ran once (2 turns), never again.
    assert sum(c["system"][0]["text"] == TEST_SYSTEM for c in calls) == 2
    # Guardian reviewed evidence (the diff), not Builder's conversation.
    review_input = [c for c in calls if c["system"][0]["text"] == GUARDIAN_SYSTEM][0]
    assert "+    return {2: 4}.get(x, 0)" in review_input["messages"][0]["content"]


def test_inspection_criterion_still_unmet_after_revise_escalates(tmp_path, project):
    store = Store(tmp_path / "ezra.db")
    envelope = TaskEnvelope(
        target_department=Department.CODE_JOE, description="Add double(x)",
        project_ref=str(project),
        acceptance_criteria=[
            AcceptanceCriterion(id="AC1", text="double(2) returns 4", severity=Severity.CRITICAL,
                                verification=Verification.TEST),
            AcceptanceCriterion(id="AC2", text="double has a docstring", severity=Severity.MAJOR,
                                verification=Verification.INSPECTION)],
        budget=Budget(task_limit_usd=2.0, daily_limit_usd=10.0))
    store.save_task(envelope)
    no_doc = guardian(criteria=[("AC2", "unmet")], corrections=["Add a docstring to double."])
    out, gw = run(store, tmp_path, {
        PLAN_SYSTEM: [message(PLAN_JSON)],
        BUILD_SYSTEM: [writes("calc.py", GOOD), message("a"), writes("calc.py", GOOD),
                       message("b")],
        TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("t")],
        GUARDIAN_SYSTEM: [no_doc, no_doc],
    }, envelope.task_id)
    reviews = store.reviews_for_task(envelope.task_id)
    assert [r.verdict for r in reviews] == ["REVISE", "ESCALATE"]
    assert reviews[1].matched_rule == 8 and out.status is TaskStatus.ESCALATED
    assert sum(c["system"][0]["text"] == BUILD_SYSTEM for c in gw.client.messages.calls) == 4
    store.close()


def _cli(monkeypatch, store_path, tmp, scripts):
    from ezra import cli
    monkeypatch.setattr(core, "open_store", lambda: Store(store_path))
    monkeypatch.setattr(core, "open_gateway", lambda store: _gw(store, scripts))
    real_run, real_answer = core.run_task, core.answer_hold
    monkeypatch.setattr(core, "run_task", lambda *a, **k: real_run(*a, **k, **_paths(tmp)))
    monkeypatch.setattr(core, "answer_hold", lambda *a, **k: real_answer(*a, **k, **_paths(tmp)))
    return cli


def test_cli_run_prints_the_pass_verdict(env, monkeypatch, capsys):
    store, envelope, tmp = env
    cli = _cli(monkeypatch, tmp / "ezra.db", tmp, SCRIPTS)
    assert cli.main(["run", envelope.task_id]) == cli.EXIT_OK
    out, err = capsys.readouterr()
    assert "Guardian verdict: PASS (rule 9, tier2_checklist)." in out
    assert "Tests 2/2 passed" in out and "AC1: met" in out
    assert f"Merging ezra/{envelope.task_id} is your call." in out
    assert "PASS: ready for you" in err  # step progress


def test_cli_run_prints_escalation_and_exits_1(env, monkeypatch, capsys):
    store, envelope, tmp = env
    code_fault = json.dumps({"fault": "code", "reason": "wrong", "builder_instructions": "fix",
                             "tester_instructions": ""})
    cli = _cli(monkeypatch, tmp / "ezra.db", tmp, {
        PLAN_SYSTEM: [message(PLAN_JSON)],
        BUILD_SYSTEM: [m for i in range(5) for m in (writes("calc.py", WRONG), message(str(i)))],
        TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("t")],
        ADJUDICATE_SYSTEM: [message(code_fault), message(code_fault)],
    })
    assert cli.main(["run", envelope.task_id]) == cli.EXIT_ERROR
    out, _ = capsys.readouterr()
    assert "Guardian verdict: ESCALATE after one REVISE (rule 4, tier1_deterministic)." in out
    assert "AC1: unmet" in out and "Escalated to you" in out


def test_cli_hold_then_approve(env, monkeypatch, capsys):
    store, envelope, tmp = env
    cli = _cli(monkeypatch, tmp / "ezra.db", tmp, SCRIPTS)
    assert cli.main(["run", envelope.task_id, "--task-budget", "0.05"]) == cli.EXIT_HOLD
    out, _ = capsys.readouterr()
    approval_id = out.split("ezra approve ")[1].split()[0]
    assert cli.main(["approve", approval_id, "--extend", "1.95"]) == cli.EXIT_OK
    assert "Guardian verdict: PASS" in capsys.readouterr().out


def test_guardian_answer_is_filtered_to_what_it_was_asked(env, project):
    from ezra.contracts import CommandRun, ResultStatus, StandardDepartmentResult
    from ezra.guardian.tier2 import run_tier2
    store, envelope, tmp = env
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True,
                          text=True).stdout.strip()
    result = StandardDepartmentResult(
        task_id=envelope.task_id, source_department=Department.CODE_JOE,
        status=ResultStatus.COMPLETED, summary="s", worktree_path=str(project),
        command_runs=[CommandRun(command="pytest", exit_code=0)])
    # Guardian re-judges a settled criterion, invents one, and repeats itself: only the
    # first judgment on a criterion it was asked about may count.
    reply = guardian(criteria=[("AC1", "unmet"), ("AC9", "met"), ("AC2", "met"),
                               ("AC2", "unmet")])
    out = run_tier2(_gw(store, {GUARDIAN_SYSTEM: [reply]}).call, envelope, result,
                    settled=[], pending=["AC2"], base_commit=head)
    assert [(r.criterion_id, r.status) for r in out.criteria_results] == [("AC2", "met")]


def test_cli_task_shows_the_verdict(env, monkeypatch, capsys):
    store, envelope, tmp = env
    cli = _cli(monkeypatch, tmp / "ezra.db", tmp, SCRIPTS)
    cli.main(["run", envelope.task_id])
    capsys.readouterr()
    assert cli.main(["task", envelope.task_id]) == cli.EXIT_OK
    shown = capsys.readouterr().out
    assert "[done]" in shown and "Review 1: PASS (rule 9, tier2_checklist)" in shown
