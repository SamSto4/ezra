"""The D-002 verdict table as pure code.

Rules are evaluated top to bottom; the first match wins. No model calls happen here, so the
same inputs always give the same verdict, and every row is unit tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ezra.contracts import (
    AcceptanceCriterion,
    CriterionResult,
    CriterionStatus,
    Department,
    Finding,
    GuardianReview,
    QualityGrade,
    ReviewTier,
    Severity,
    Verdict,
)


@dataclass(frozen=True)
class VerdictInput:
    criteria: list[AcceptanceCriterion]
    criteria_results: list[CriterionResult]
    findings: list[Finding] = field(default_factory=list)
    grade: QualityGrade | None = None  # None = ungraded (Tier 1 / Tier 2)
    # Criteria not evaluated yet (Tier 2 skipped by a Tier 1 short-circuit). They are left out
    # of the decision instead of being reported as unmet, and they can never produce a PASS.
    pending: frozenset[str] = frozenset()
    correction_budget_left: bool = True
    authorization_unresolved: bool = False


@dataclass(frozen=True)
class VerdictDecision:
    verdict: Verdict
    matched_rule: int
    reason: str
    unmet: dict[Severity, list[str]]  # severity -> criterion ids treated as unmet
    notes: list[str]  # minor issues attached to a PASS


def effective_status(
    criteria: list[AcceptanceCriterion], results: list[CriterionResult]
) -> dict[str, CriterionStatus]:
    """Status per criterion id. Missing or cannot_verify results count as UNMET."""
    known = {c.id for c in criteria}
    ids = [r.criterion_id for r in results]
    unknown = set(ids) - known
    if unknown:
        raise ValueError(f"results reference unknown criteria: {sorted(unknown)}")
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        # A later "met" must never silently overwrite an earlier "unmet".
        raise ValueError(f"more than one result for criteria: {dupes}")
    by_id = {r.criterion_id: r.status for r in results}
    out: dict[str, CriterionStatus] = {}
    for c in criteria:
        status = by_id.get(c.id, CriterionStatus.CANNOT_VERIFY)
        out[c.id] = CriterionStatus.MET if status is CriterionStatus.MET else CriterionStatus.UNMET
    return out


def decide(inp: VerdictInput) -> VerdictDecision:
    decision = _decide(inp)
    if inp.pending and decision.verdict is Verdict.PASS:
        raise ValueError(f"cannot PASS with uninspected criteria: {sorted(inp.pending)}")
    return decision


def _decide(inp: VerdictInput) -> VerdictDecision:
    unknown_pending = inp.pending - {c.id for c in inp.criteria}
    if unknown_pending:
        raise ValueError(f"pending references unknown criteria: {sorted(unknown_pending)}")
    evaluated = [c for c in inp.criteria if c.id not in inp.pending]
    status = effective_status(evaluated, inp.criteria_results)
    unmet: dict[Severity, list[str]] = {s: [] for s in Severity}
    for c in evaluated:
        if status[c.id] is CriterionStatus.UNMET:
            unmet[c.severity].append(c.id)

    findings_by_sev = {s: [f for f in inp.findings if f.severity is s] for s in Severity}
    has_critical = bool(unmet[Severity.CRITICAL] or findings_by_sev[Severity.CRITICAL])
    has_major = bool(unmet[Severity.MAJOR] or findings_by_sev[Severity.MAJOR])
    budget = inp.correction_budget_left
    graded = inp.grade is not None

    def out(verdict: Verdict, rule: int, reason: str, notes: list[str] | None = None):
        return VerdictDecision(verdict, rule, reason, unmet, notes or [])

    # Row 1: authorization unresolved
    if inp.authorization_unresolved:
        return out(Verdict.HOLD, 1, "authorization or permission requirement unresolved")

    # Row 2: cannot be safely fixed automatically
    not_fixable = [f.code for f in inp.findings if not f.auto_fixable]
    if not_fixable:
        return out(Verdict.ESCALATE, 2, f"not safely fixable automatically: {not_fixable}")

    # Rows 3-4: critical failure
    if has_critical:
        what = unmet[Severity.CRITICAL] + [f.code for f in findings_by_sev[Severity.CRITICAL]]
        if budget:
            return out(Verdict.REVISE, 3, f"critical failure: {what}")
        return out(Verdict.ESCALATE, 4, f"critical failure, no correction budget: {what}")

    # Rows 5-6: grade fail (graded outputs only)
    if graded and inp.grade is QualityGrade.FAIL:
        if budget:
            return out(Verdict.REVISE, 5, "quality grade: fail")
        return out(Verdict.ESCALATE, 6, "quality grade: fail, no correction budget")

    # Rows 7-8: unmet major criterion / major finding, or grade conditional (graded only)
    conditional = graded and inp.grade is QualityGrade.CONDITIONAL
    if has_major or conditional:
        what = unmet[Severity.MAJOR] + [f.code for f in findings_by_sev[Severity.MAJOR]]
        reason = f"major issues: {what}" if what else "quality grade: conditional"
        if budget:
            return out(Verdict.REVISE, 7, reason)
        return out(Verdict.ESCALATE, 8, reason + ", no correction budget")

    # Row 9: everything else passes; minor issues become notes
    notes = [f"unmet minor criterion {cid}" for cid in unmet[Severity.MINOR]]
    notes += [f"{f.code}: {f.message}" for f in findings_by_sev[Severity.MINOR]]
    return out(Verdict.PASS, 9, "all critical and major requirements met", notes)


def build_review(
    *,
    task_id: str,
    source_department: Department,
    tier: ReviewTier,
    inp: VerdictInput,
    required_corrections: list[str] | None = None,
    summary: str = "",
) -> GuardianReview:
    decision = decide(inp)
    corrections = list(required_corrections or [])
    if decision.verdict is Verdict.REVISE and not corrections:
        corrections = [decision.reason]
    return GuardianReview(
        task_id=task_id,
        source_department=source_department,
        tier=tier,
        criteria_results=inp.criteria_results,
        findings=inp.findings,
        grade=inp.grade,
        verdict=decision.verdict,
        matched_rule=decision.matched_rule,
        required_corrections=corrections if decision.verdict is Verdict.REVISE else [],
        summary=summary or decision.reason + (f" | notes: {decision.notes}" if decision.notes
                                               else ""),
    )
