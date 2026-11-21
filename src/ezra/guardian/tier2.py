"""Guardian Tier 2: a checklist review by a model (D-007).

Guardian reviews evidence, not transcripts: the task, the criteria with what Tier 1 already
proved, the diff and the test results. It never sees Builder's or Tester's conversations.
It runs on a different model family member (Opus) than Builder (Sonnet), so their blind
spots are less likely to line up.

Two jobs in one structured call:
1. Judge each criterion Tier 1 couldn't (verification "inspection"): met / unmet /
   cannot_verify, with cited evidence.
2. Look for problems outside the criteria: special-casing test inputs, broken constraints,
   unrelated changes, obvious bugs the tests miss. These become findings.

The verdict itself is never the model's: the D-002 table in verdict.py decides it from
these results.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from ezra.code_joe.agents import _schema, criteria_text
from ezra.code_joe.tools import AgentError
from ezra.contracts import (
    CommandRun,
    CriterionResult,
    CriterionStatus,
    Department,
    Finding,
    ModelInvocation,
    Severity,
    StandardDepartmentResult,
    TaskEnvelope,
)

OPERATION = "guardian.tier2"
MAX_TOKENS = 8_000
DIFF_CHARS = 30_000


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckItem(_M):
    criterion_id: str
    status: Literal["met", "unmet", "cannot_verify"]
    evidence: str


class FindingItem(_M):
    code: str
    severity: Literal["critical", "major", "minor"]
    message: str
    auto_fixable: bool


class Tier2Answer(_M):
    criteria: list[CheckItem]
    findings: list[FindingItem]
    required_corrections: list[str]
    summary: str


SCHEMA = _schema(Tier2Answer)

SYSTEM = """\
You are Guardian, Ezra's independent reviewer. A coding department submitted work on a git
branch. You review the evidence and report facts; a fixed rule table turns your report into
the verdict, so don't argue for one.

You get: the task, its Acceptance Criteria with what automatic checks already proved, the
constraints, the diff against the base commit, and the test results.

1. criteria: judge ONLY the criteria listed under "Criteria for you to judge". For each:
   "met" (the diff shows it), "unmet" (the diff shows it isn't), or "cannot_verify" (the
   evidence isn't there). Quote or point to the line in "evidence". Don't re-judge criteria
   the automatic checks already settled.

2. findings: problems outside the criteria. Look for:
   - code that special-cases the inputs used in tests or criteria instead of implementing
     the behavior (lookup tables of expected answers, `if text == "..."` branches),
   - a broken constraint (new dependency, changed behavior that was meant to stay the same),
   - changes to files unrelated to the task,
   - clear bugs on inputs the tests don't cover, if the criteria imply that behavior,
   - security problems (running shell commands, reading secrets, network calls).
   Severity: "critical" only if the work is unsafe or useless; "major" if it must be fixed
   before acceptance (special-casing, broken constraint, real bug); "minor" for style or
   polish. Set auto_fixable to false only if fixing it needs the user's input. Use short
   snake_case codes such as "special_cases_test_inputs". Report nothing you aren't sure of;
   an empty list is a good answer.

3. required_corrections: for every unmet criterion and every critical or major finding, one
   concrete instruction Builder can act on without seeing this review. Leave it empty if
   there's nothing to fix.

4. summary: one or two sentences.
"""


@dataclass
class Tier2Outcome:
    criteria_results: list[CriterionResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    required_corrections: list[str] = field(default_factory=list)
    summary: str = ""
    invocations: list[ModelInvocation] = field(default_factory=list)


def diff_evidence(worktree: Path, base_commit: str) -> str:
    diff = subprocess.run(["git", "diff", base_commit, "HEAD"], cwd=worktree,
                          capture_output=True, text=True, check=True).stdout
    return diff if len(diff) <= DIFF_CHARS else diff[:DIFF_CHARS] + "\n…(diff cut)"


def test_evidence(runs: list[CommandRun]) -> str:
    lines = []
    for r in runs:
        status = "timed out" if r.timed_out else f"exit code {r.exit_code}"
        lines.append(f"{r.command}: {status}")
        lines += [f"  {c.outcome}: {c.name}" for c in r.cases]
        if r.command == "ruff" and r.exit_code not in (0, None):
            lines.append(r.output_excerpt[-1500:])
    return "\n".join(lines)


def run_tier2(call: Callable[..., Any], env: TaskEnvelope, result: StandardDepartmentResult,
              settled: list[CriterionResult], pending: list[str], base_commit: str
              ) -> Tier2Outcome:
    settled_text = "\n".join(f"- {r.criterion_id}: {r.status}" + (f" ({r.evidence})"
                                                                   if r.evidence else "")
                             for r in settled) or "- none"
    to_judge = [c for c in env.acceptance_criteria if c.id in pending]
    diff = diff_evidence(Path(result.worktree_path), base_commit)
    tests = test_evidence(result.command_runs)
    user = (f"## Task\n{env.description}\n\n## Acceptance criteria\n"
            f"{criteria_text(env.acceptance_criteria)}\n\n## Already settled by automatic "
            f"checks\n{settled_text}\n\n## Criteria for you to judge\n"
            f"{criteria_text(to_judge) or '- none (report findings only)'}\n\n"
            "## Constraints\n" + ("\n".join(f"- {c}" for c in env.constraints) or "- none")
            + "\n\n## Changed files\n" + "\n".join(f"- {f}" for f in result.changed_files)
            + f"\n\n## Test results\n{tests}\n\n## Diff\n```diff\n{diff}\n```")
    resp = call(operation=OPERATION, department=Department.GUARDIAN, system=SYSTEM,
                messages=[{"role": "user", "content": user}], max_tokens=MAX_TOKENS,
                task_id=env.task_id, output_format={"type": "json_schema", "schema": SCHEMA},
                context=[("task", env.description),
                         ("criteria", criteria_text(env.acceptance_criteria)),
                         ("settled_by_tier1", settled_text), ("test_results", tests),
                         ("diff", diff)])
    invs = [resp.invocation]
    if resp.truncated or not resp.text.strip():
        raise AgentError("Guardian's review was cut off or empty", invs)
    try:
        answer = Tier2Answer.model_validate_json(resp.text)
    except ValidationError as e:
        raise AgentError(f"Guardian's review didn't match its schema: {e}", invs) from e

    # Keep only judgments on criteria Guardian was asked about, one per criterion. A missing
    # one simply stays missing: the verdict table treats it as unmet.
    seen: dict[str, CriterionResult] = {}
    for item in answer.criteria:
        if item.criterion_id in pending and item.criterion_id not in seen:
            seen[item.criterion_id] = CriterionResult(
                criterion_id=item.criterion_id, status=CriterionStatus(item.status),
                evidence=item.evidence[:500])
    return Tier2Outcome(
        criteria_results=list(seen.values()),
        findings=[Finding(code=f.code[:60], severity=Severity(f.severity),
                          message=f.message[:500], auto_fixable=f.auto_fixable)
                  for f in answer.findings],
        required_corrections=[c[:600] for c in answer.required_corrections][:10],
        summary=answer.summary[:500], invocations=invs)
