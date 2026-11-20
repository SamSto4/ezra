"""Guardian Tier 1 deterministic checks."""

from conftest import crit, envelope

from ezra.contracts import (
    CommandRun,
    CriterionStatus,
    Department,
    DeterministicCheck,
    ResultStatus,
    Severity,
    StandardDepartmentResult,
    TestCaseResult,
    Verification,
)
from ezra.guardian.tier1 import criterion_pattern, is_acceptance_case, run_tier1

A = "tests/acceptance/test_task.py"


def pytest_run(*cases, exit_code=0, timed_out=False):
    return CommandRun(command="pytest", exit_code=None if timed_out else exit_code,
                      timed_out=timed_out,
                      cases=[TestCaseResult(name=n, outcome=o) for n, o in cases])


def result(env, runs=(), changed=(), worktree="/tmp/wt", task_id=None):
    return StandardDepartmentResult(
        task_id=task_id or env.task_id, source_department=Department.CODE_JOE,
        status=ResultStatus.COMPLETED, summary="done", worktree_path=worktree,
        changed_files=list(changed), command_runs=list(runs))


def statuses(outcome):
    return {r.criterion_id: r.status for r in outcome.criteria_results}


def test_criterion_pattern_does_not_confuse_ac1_and_ac10():
    p = criterion_pattern("AC1")
    assert p.search("tests/acceptance/test_x.py::test_ac1_counts")
    assert p.search("test_AC1")
    assert not p.search("test_ac10_other")
    assert not p.search("test_bac1")


def test_test_criteria_mapped_from_test_names():
    env = envelope([crit("AC1"), crit("AC2"), crit("AC3")])
    run = pytest_run((f"{A}::test_ac1_a", "passed"), (f"{A}::test_ac1_b", "passed"),
                     (f"{A}::test_ac2_a", "failed"), exit_code=1)
    out = run_tier1(env, result(env, [run]))
    assert statuses(out) == {"AC1": CriterionStatus.MET, "AC2": CriterionStatus.UNMET,
                             "AC3": CriterionStatus.CANNOT_VERIFY}
    assert out.short_circuit  # AC2 (major) is unmet: no need to pay for Tier 2


def test_all_skipped_cannot_verify():
    env = envelope([crit("AC1")])
    out = run_tier1(env, result(env, [pytest_run((f"{A}::test_ac1", "skipped"))]))
    assert statuses(out)["AC1"] is CriterionStatus.CANNOT_VERIFY


def test_broken_or_timed_out_run_cannot_verify_and_is_a_major_finding():
    env = envelope([crit("AC1")])
    for run in (pytest_run((f"{A}::test_ac1", "passed"), exit_code=2),
                pytest_run(timed_out=True)):
        out = run_tier1(env, result(env, [run]))
        assert statuses(out)["AC1"] is CriterionStatus.CANNOT_VERIFY
        assert [f.code for f in out.findings] == ["pytest_run_broken"]


def test_deterministic_checks():
    env = envelope([
        crit("AC1", verification=Verification.DETERMINISTIC, check=DeterministicCheck.TESTS_PASS),
        crit("AC2", verification=Verification.DETERMINISTIC, check=DeterministicCheck.LINT_CLEAN),
    ])
    runs = [pytest_run(("test_x", "passed")),
            CommandRun(command="ruff", exit_code=1, output_excerpt="E501 line too long")]
    out = run_tier1(env, result(env, runs))
    assert statuses(out) == {"AC1": CriterionStatus.MET, "AC2": CriterionStatus.UNMET}


def test_inspection_criteria_left_for_tier2():
    env = envelope([crit("AC1", verification=Verification.INSPECTION)])
    out = run_tier1(env, result(env))
    assert out.pending_inspection == ["AC1"] and out.criteria_results == []
    assert not out.short_circuit


def test_task_id_mismatch_is_critical_and_not_auto_fixable():
    env = envelope([])
    out = run_tier1(env, result(env, task_id="task_other"))
    f = out.findings[0]
    assert (f.code, f.severity, f.auto_fixable) == ("task_id_mismatch", Severity.CRITICAL, False)


def test_changed_file_outside_worktree_is_caught(tmp_path):
    env = envelope([])
    wt = tmp_path / "wt"
    wt.mkdir()
    out = run_tier1(env, result(env, changed=["ok.py", "../escape.py"], worktree=str(wt)))
    assert [f.code for f in out.findings] == ["write_outside_worktree"]


def test_minor_unmet_does_not_short_circuit():
    env = envelope([crit("AC1", Severity.MINOR)])
    out = run_tier1(env, result(env, [pytest_run((f"{A}::test_ac1", "failed"), exit_code=1)]))
    assert statuses(out)["AC1"] is CriterionStatus.UNMET
    assert not out.short_circuit


def test_only_protected_acceptance_tests_count_as_evidence():
    # Builder could write tests/test_ac1_fake.py; it must not turn AC1 into "met".
    env = envelope([crit("AC1")])
    run = pytest_run(("tests/test_ac1_fake.py::test_ac1", "passed"))
    out = run_tier1(env, result(env, [run]))
    assert statuses(out)["AC1"] is CriterionStatus.CANNOT_VERIFY


def test_is_acceptance_case():
    assert is_acceptance_case("tests/acceptance/test_x.py::test_ac1")
    assert is_acceptance_case("Tests/Acceptance/test_x.py::test_ac1")
    assert not is_acceptance_case("tests/test_x.py::test_ac1")
    assert not is_acceptance_case("tests/acceptance_fake/test_x.py::test_ac1")
