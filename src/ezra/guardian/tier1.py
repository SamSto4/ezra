"""Guardian Tier 1: deterministic checks, zero model tokens (D-007).

Checks the integrity of a Code Joe result and evaluates every Acceptance Criterion that code
can decide (test-verified and deterministic criteria). Inspection criteria are left for Tier 2.
If Tier 1 already finds a critical or major problem, the verdict is decided here and Tier 2 is
skipped (D-007, "deterministic first, short-circuit").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ezra.code_joe.workspace import ACCEPTANCE_TEST_DIR, is_within
from ezra.contracts import (
    AcceptanceCriterion,
    CommandRun,
    CriterionResult,
    CriterionStatus,
    DeterministicCheck,
    Finding,
    Severity,
    StandardDepartmentResult,
    TaskEnvelope,
    Verification,
)

# pytest exit codes: 0 all passed, 1 some failed, anything else means the run itself broke.
PYTEST_OK = {0, 1}
RUFF_OK = {0, 1}


@dataclass
class Tier1Outcome:
    criteria_results: list[CriterionResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    pending_inspection: list[str] = field(default_factory=list)  # criterion ids for Tier 2
    blocking_ids: set[str] = field(default_factory=set)  # critical + major criterion ids

    @property
    def short_circuit(self) -> bool:
        """True when the verdict can be decided without a Tier 2 model call."""
        if any(f.severity in (Severity.CRITICAL, Severity.MAJOR) for f in self.findings):
            return True
        return any(r.status is not CriterionStatus.MET for r in self.criteria_results
                   if r.criterion_id in self.blocking_ids)


def criterion_pattern(criterion_id: str) -> re.Pattern[str]:
    """Matches 'ac1' in test names like test_ac1_counts_words but not 'ac10'."""
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(criterion_id)}(?!\d)", re.IGNORECASE)


def is_acceptance_case(name: str) -> bool:
    """Only Tester's protected acceptance tests count as evidence for a criterion.

    Builder can write other tests, so a test named test_ac2 elsewhere must not mark AC2 met.
    """
    path = name.split("::", 1)[0].replace("\\", "/").casefold()
    return path.startswith(ACCEPTANCE_TEST_DIR.casefold() + "/")


def _last_run(result: StandardDepartmentResult, command: str) -> CommandRun | None:
    runs = [r for r in result.command_runs if r.command == command]
    return runs[-1] if runs else None


def _run_broken(run: CommandRun, ok_codes: set[int]) -> bool:
    return run.timed_out or run.exit_code is None or run.exit_code not in ok_codes


def _eval_test_criterion(c: AcceptanceCriterion, pytest_run: CommandRun | None) -> CriterionResult:
    if pytest_run is None or _run_broken(pytest_run, PYTEST_OK):
        return CriterionResult(criterion_id=c.id, status=CriterionStatus.CANNOT_VERIFY,
                               evidence="no usable pytest run")
    pat = criterion_pattern(c.id)
    cases = [t for t in pytest_run.cases if is_acceptance_case(t.name) and pat.search(t.name)]
    if not cases:
        return CriterionResult(criterion_id=c.id, status=CriterionStatus.CANNOT_VERIFY,
                               evidence=f"no acceptance test name references {c.id}")
    failing = [t.name for t in cases if t.outcome in ("failed", "error")]
    if failing:
        return CriterionResult(criterion_id=c.id, status=CriterionStatus.UNMET,
                               evidence=f"failing: {failing}")
    if all(t.outcome == "skipped" for t in cases):
        return CriterionResult(criterion_id=c.id, status=CriterionStatus.CANNOT_VERIFY,
                               evidence=f"all {len(cases)} tests skipped")
    passed = [t.name for t in cases if t.outcome == "passed"]
    return CriterionResult(criterion_id=c.id, status=CriterionStatus.MET,
                           evidence=f"passed: {passed}")


def _eval_deterministic(c: AcceptanceCriterion, result: StandardDepartmentResult
                        ) -> CriterionResult:
    command, ok = {
        DeterministicCheck.TESTS_PASS: ("pytest", PYTEST_OK),
        DeterministicCheck.LINT_CLEAN: ("ruff", RUFF_OK),
    }[c.check]  # type: ignore[index]
    run = _last_run(result, command)
    if run is None or _run_broken(run, ok):
        return CriterionResult(criterion_id=c.id, status=CriterionStatus.CANNOT_VERIFY,
                               evidence=f"no usable {command} run")
    if run.exit_code == 0:
        return CriterionResult(criterion_id=c.id, status=CriterionStatus.MET,
                               evidence=f"{command} exit code 0")
    return CriterionResult(criterion_id=c.id, status=CriterionStatus.UNMET,
                           evidence=f"{command} exit code {run.exit_code}: "
                                    f"{run.output_excerpt[:300]}")


def run_tier1(envelope: TaskEnvelope, result: StandardDepartmentResult) -> Tier1Outcome:
    outcome = Tier1Outcome()

    # --- integrity checks -----------------------------------------------------
    if result.task_id != envelope.task_id:
        outcome.findings.append(Finding(
            code="task_id_mismatch", severity=Severity.CRITICAL, auto_fixable=False,
            message=f"result task_id {result.task_id} != envelope {envelope.task_id}"))

    if result.changed_files:
        if not result.worktree_path:
            outcome.findings.append(Finding(
                code="no_worktree", severity=Severity.CRITICAL, auto_fixable=False,
                message="code changes reported without a worktree path"))
        else:
            root = Path(result.worktree_path)
            escaped = [f for f in result.changed_files if not is_within(root, f)]
            if escaped:
                outcome.findings.append(Finding(
                    code="write_outside_worktree", severity=Severity.CRITICAL,
                    auto_fixable=False, message=f"changed files outside worktree: {escaped}"))

    pytest_run = _last_run(result, "pytest")
    for cmd, ok in (("pytest", PYTEST_OK), ("ruff", RUFF_OK)):
        run = _last_run(result, cmd)
        if run is not None and _run_broken(run, ok):
            why = "timed out" if run.timed_out else f"exit code {run.exit_code}"
            outcome.findings.append(Finding(
                code=f"{cmd}_run_broken", severity=Severity.MAJOR,
                message=f"{cmd} run did not complete normally ({why})"))

    # --- criteria code can decide -----------------------------------------
    for c in envelope.acceptance_criteria:
        if c.verification is Verification.TEST:
            outcome.criteria_results.append(_eval_test_criterion(c, pytest_run))
        elif c.verification is Verification.DETERMINISTIC:
            outcome.criteria_results.append(_eval_deterministic(c, result))
        else:
            outcome.pending_inspection.append(c.id)

    outcome.blocking_ids = {c.id for c in envelope.acceptance_criteria
                             if c.severity in (Severity.CRITICAL, Severity.MAJOR)}
    return outcome
