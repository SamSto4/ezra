"""Every row of the D-002 verdict table, plus edge cases."""

import pytest
from conftest import crit, envelope

from ezra.contracts import (
    CriterionResult,
    CriterionStatus,
    Department,
    Finding,
    QualityGrade,
    ReviewTier,
    Severity,
    Verdict,
)
from ezra.guardian.verdict import VerdictInput, build_review, decide

MET, UNMET, CV = CriterionStatus.MET, CriterionStatus.UNMET, CriterionStatus.CANNOT_VERIFY


def res(cid, status):
    return CriterionResult(criterion_id=cid, status=status)


CRITERIA = [crit("AC1", Severity.CRITICAL), crit("AC2", Severity.MAJOR),
            crit("AC3", Severity.MINOR)]
ALL_MET = [res("AC1", MET), res("AC2", MET), res("AC3", MET)]


def run(results=ALL_MET, findings=(), grade=None, budget=True, auth=False):
    return decide(VerdictInput(criteria=CRITERIA, criteria_results=list(results),
                               findings=list(findings), grade=grade,
                               correction_budget_left=budget, authorization_unresolved=auth))


def test_row1_hold_beats_everything():
    d = run(results=[res("AC1", UNMET)], auth=True)
    assert (d.verdict, d.matched_rule) == (Verdict.HOLD, 1)


def test_row2_not_auto_fixable_escalates_even_with_budget():
    f = Finding(code="write_outside_worktree", severity=Severity.CRITICAL,
                message="x", auto_fixable=False)
    d = run(findings=[f], budget=True)
    assert (d.verdict, d.matched_rule) == (Verdict.ESCALATE, 2)


@pytest.mark.parametrize("budget,verdict,rule", [(True, Verdict.REVISE, 3),
                                                 (False, Verdict.ESCALATE, 4)])
def test_rows3_4_unmet_critical_criterion(budget, verdict, rule):
    d = run(results=[res("AC1", UNMET), res("AC2", MET), res("AC3", MET)], budget=budget)
    assert (d.verdict, d.matched_rule) == (verdict, rule)


def test_row3_critical_finding_counts_as_critical_failure():
    f = Finding(code="secret_leak", severity=Severity.CRITICAL, message="x")
    assert run(findings=[f]).matched_rule == 3


@pytest.mark.parametrize("budget,verdict,rule", [(True, Verdict.REVISE, 5),
                                                 (False, Verdict.ESCALATE, 6)])
def test_rows5_6_grade_fail(budget, verdict, rule):
    d = run(grade=QualityGrade.FAIL, budget=budget)
    assert (d.verdict, d.matched_rule) == (verdict, rule)


@pytest.mark.parametrize("budget,verdict,rule", [(True, Verdict.REVISE, 7),
                                                 (False, Verdict.ESCALATE, 8)])
def test_rows7_8_unmet_major_criterion_ungraded(budget, verdict, rule):
    # The Tier 2 hole fixed in D-002: no grade, but an unmet major criterion still blocks.
    d = run(results=[res("AC1", MET), res("AC2", UNMET), res("AC3", MET)], budget=budget)
    assert (d.verdict, d.matched_rule) == (verdict, rule)


@pytest.mark.parametrize("budget,verdict,rule", [(True, Verdict.REVISE, 7),
                                                 (False, Verdict.ESCALATE, 8)])
def test_rows7_8_grade_conditional(budget, verdict, rule):
    d = run(grade=QualityGrade.CONDITIONAL, budget=budget)
    assert (d.verdict, d.matched_rule) == (verdict, rule)


def test_row7_major_finding():
    f = Finding(code="ruff_run_broken", severity=Severity.MAJOR, message="x")
    assert run(findings=[f]).matched_rule == 7


@pytest.mark.parametrize("grade", [None, QualityGrade.PASS, QualityGrade.EXCELLENT])
def test_row9_pass(grade):
    d = run(grade=grade)
    assert (d.verdict, d.matched_rule) == (Verdict.PASS, 9)
    assert d.notes == []


def test_row9_pass_with_minor_notes_and_no_budget():
    f = Finding(code="style", severity=Severity.MINOR, message="long line")
    d = run(results=[res("AC1", MET), res("AC2", MET), res("AC3", UNMET)], findings=[f],
            budget=False)
    assert d.verdict is Verdict.PASS
    assert len(d.notes) == 2


def test_cannot_verify_counts_as_unmet():
    d = run(results=[res("AC1", CV), res("AC2", MET), res("AC3", MET)])
    assert d.matched_rule == 3 and d.unmet[Severity.CRITICAL] == ["AC1"]


def test_missing_result_counts_as_unmet():
    d = run(results=[res("AC1", MET), res("AC3", MET)])  # AC2 never evaluated
    assert d.matched_rule == 7 and d.unmet[Severity.MAJOR] == ["AC2"]


def test_unknown_criterion_id_is_a_contract_error():
    with pytest.raises(ValueError):
        run(results=[*ALL_MET, res("AC9", MET)])


def test_critical_outranks_grade_and_major():
    d = run(results=[res("AC1", UNMET), res("AC2", UNMET), res("AC3", MET)],
            grade=QualityGrade.FAIL)
    assert d.matched_rule == 3


def test_build_review_attaches_corrections_only_on_revise():
    inp = VerdictInput(criteria=CRITERIA,
                       criteria_results=[res("AC1", MET), res("AC2", UNMET), res("AC3", MET)])
    review = build_review(task_id="task_x", source_department=Department.CODE_JOE,
                          tier=ReviewTier.CHECKLIST, inp=inp)
    assert review.verdict is Verdict.REVISE and review.required_corrections

    ok = build_review(task_id="task_x", source_department=Department.CODE_JOE,
                      tier=ReviewTier.CHECKLIST,
                      inp=VerdictInput(criteria=CRITERIA, criteria_results=ALL_MET),
                      required_corrections=["ignored"])
    assert ok.verdict is Verdict.PASS and ok.required_corrections == []


def test_duplicate_results_rejected_so_met_cannot_overwrite_unmet():
    with pytest.raises(ValueError):
        run(results=[*ALL_MET, res("AC2", UNMET)])


def test_duplicate_criterion_ids_rejected_in_envelope():
    with pytest.raises(ValueError):
        envelope([crit("AC1"), crit("AC1")])


def test_pending_inspection_criteria_are_not_reported_as_unmet():
    # Tier 1 short-circuit: AC2 failed its test; AC3 (inspection) was never looked at.
    d = decide(VerdictInput(criteria=CRITERIA,
                            criteria_results=[res("AC1", MET), res("AC2", UNMET)],
                            pending=frozenset({"AC3"})))
    assert d.matched_rule == 7
    assert d.unmet[Severity.MINOR] == []  # AC3 is not blamed


def test_pending_criteria_can_never_pass():
    with pytest.raises(ValueError):
        decide(VerdictInput(criteria=CRITERIA,
                            criteria_results=[res("AC1", MET), res("AC2", MET)],
                            pending=frozenset({"AC3"})))
