"""Ezra intake: one structured model call that routes a request.

Routes:
- direct:      answer now (Tier 0, no review). Also used to ask a clarifying question.
- code:        write Acceptance Criteria and create a TaskEnvelope for Code Joe.
- unsupported: explain that the capability isn't built yet.

One call does routing, answering and criteria writing, which is cheaper than three calls.
The system prompt is static (no dates or ids) so it can be cached; the request and the
project summary go in the user message, after the cached prefix.
"""

from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ezra.contracts import (
    AcceptanceCriterion,
    Budget,
    Department,
    DeterministicCheck,
    Limits,
    LoopCounters,
    ModelInvocation,
    Severity,
    TaskEnvelope,
    Verification,
    new_id,
)
from ezra.gateway import Gateway

OPERATION = "ezra.intake"
MAX_TOKENS = 8000
MAX_REPAIRS = 1
MAX_CRITERIA = 8


class Route(StrEnum):
    DIRECT = "direct"
    CODE = "code"
    UNSUPPORTED = "unsupported"


# -- what the model returns ------------------------------------------------------


class DraftCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    severity: Severity
    verification: Verification
    check: DeterministicCheck | None
    required_evidence: str


class IntakeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: Route
    answer: str = Field(description="direct: the full answer. Otherwise empty.")
    task_title: str = Field(description="code: a short imperative title. Otherwise empty.")
    task_description: str = Field(description="code: the goal restated precisely.")
    acceptance_criteria: list[DraftCriterion]
    constraints: list[str]
    unsupported_reason: str = Field(description="unsupported: what's missing. Otherwise empty.")


_ENUM = lambda e: {"type": "string", "enum": [m.value for m in e]}  # noqa: E731

SCHEMA = {
    "type": "object",
    "properties": {
        "route": _ENUM(Route),
        "answer": {"type": "string"},
        "task_title": {"type": "string"},
        "task_description": {"type": "string"},
        "acceptance_criteria": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "text": {"type": "string"},
                "severity": _ENUM(Severity),
                "verification": _ENUM(Verification),
                "check": {"anyOf": [_ENUM(DeterministicCheck), {"type": "null"}]},
                "required_evidence": {"type": "string"},
            },
            "required": ["id", "text", "severity", "verification", "check",
                         "required_evidence"],
            "additionalProperties": False,
        }},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "unsupported_reason": {"type": "string"},
    },
    "required": ["route", "answer", "task_title", "task_description", "acceptance_criteria",
                 "constraints", "unsupported_reason"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are Ezra's intake step. Ezra is a personal AI assistant. You read one request and decide
how Ezra handles it, filling in the JSON schema you are given.

## Routes

- "direct": a question or small request you can fully answer in text right now, such as an
  explanation, advice, a short code snippet the user will paste themselves, or a calculation.
  Put the complete answer in "answer". If a coding request is too vague to write testable
  criteria (for example "make it better"), also use "direct" and ask one specific clarifying
  question in "answer".
- "code": a change to the project described in the message (a Python package with pytest
  tests). Ezra's coding department, Code Joe, will implement it on a separate git branch.
  Code Joe can read and write files in that project only. It can't install packages, reach
  the network, or touch any other repository.
- "unsupported": anything needing capabilities Ezra doesn't have yet: email, messaging,
  calendars, web browsing or live data, files outside the project, purchases, or changes to
  other repositories. Explain briefly in "unsupported_reason".

Leave fields that don't apply to the chosen route empty ("" or []).

## Acceptance criteria (route "code" only)

Write between 2 and 8 criteria. A reviewer will check every one, so each must be:
- Specific and checkable: name the function, input and expected output where possible,
  e.g. `sentence_count("Hi. Bye.")` returns 2.
- About one behavior. Split "handles empty and None input" into two criteria.
- Faithful to the request. Don't add features the user didn't ask for.

Ids are "AC1", "AC2", ... in order, with no gaps.

severity:
- "critical": the core behavior. If it fails, the work is useless.
- "major": must be fixed before the work is accepted (important edge cases, required API
  shape, not breaking existing behavior).
- "minor": nice to have; noted but never blocks (docstrings, naming polish).
At least one criterion must be "critical".

verification:
- "test": checked by an automated acceptance test that someone else writes from this
  criterion alone. Prefer this for any behavior. The text must be precise enough to write
  that test without seeing the code.
- "deterministic": checked by a named tool. Set "check" to "tests_pass" (the project's
  whole existing test suite still passes) or "lint_clean" (ruff reports no problems).
- "inspection": checked by a reviewer reading the diff. Use only for things a test can't
  check, such as "has a docstring" or "doesn't change files other than X".
Set "check" only for "deterministic" criteria, and null for every other criterion.

Usually include one "deterministic" criterion with check "tests_pass" so existing behavior
doesn't break.

required_evidence: what proves the criterion, e.g. "acceptance test for AC1 passes".

constraints: rules the implementation must follow that the user stated or clearly implied,
e.g. "no new dependencies". Leave it empty if there are none.

task_title: imperative, under 60 characters. task_description: the goal in 1-3 sentences.
"""


# -- project context -------------------------------------------------------------------

NO_PROJECT = ("No project is available right now, so route every coding request to "
              '"unsupported".')


def project_summary(project: Path) -> str:
    """Tracked files plus the public top-level functions and classes of Python modules.
    Small, so it goes in every request without a big token cost."""
    try:
        files = subprocess.run(["git", "ls-files"], cwd=project, capture_output=True,
                               text=True, check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return NO_PROJECT
    lines = [f"Project: {project.name}", "Files:"]
    for f in files:
        lines.append(f"- {f}")
        if f.endswith(".py") and not f.startswith("tests/"):
            try:
                tree = ast.parse((project / f).read_text())
            except (OSError, SyntaxError):
                continue
            for node in tree.body:
                if isinstance(node, ast.FunctionDef | ast.ClassDef) and \
                        not node.name.startswith("_"):
                    if isinstance(node, ast.ClassDef):
                        lines.append(f"    class {node.name}")
                        continue
                    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                    lines.append(f"    def {node.name}({ast.unparse(node.args)}){ret}")
    return "\n".join(lines)


# -- results ---------------------------------------------------------------------------


class IntakeError(Exception):
    def __init__(self, message: str, invocations: list[ModelInvocation]):
        super().__init__(message)
        self.invocations = invocations


@dataclass
class IntakeResult:
    request_id: str
    route: Route
    answer: str = ""
    unsupported_reason: str = ""
    envelope: TaskEnvelope | None = None
    task_title: str = ""
    invocations: list[ModelInvocation] = field(default_factory=list)


def problems_with(decision: IntakeDecision) -> list[str]:
    """Rules the schema can't express. Each problem is sent back for one repair."""
    found: list[str] = []
    if decision.route is Route.DIRECT and not decision.answer.strip():
        found.append('route "direct" needs a non-empty "answer"')
    if decision.route is Route.UNSUPPORTED and not decision.unsupported_reason.strip():
        found.append('route "unsupported" needs an "unsupported_reason"')
    if decision.route is not Route.CODE:
        return found
    crits = decision.acceptance_criteria
    if not 2 <= len(crits) <= MAX_CRITERIA:
        found.append(f"write between 2 and {MAX_CRITERIA} acceptance criteria")
    if not decision.task_description.strip():
        found.append('route "code" needs a "task_description"')
    expected = [f"AC{i}" for i in range(1, len(crits) + 1)]
    if [c.id for c in crits] != expected:
        found.append(f"criterion ids must be {', '.join(expected)} in order")
    if crits and not any(c.severity is Severity.CRITICAL for c in crits):
        found.append('at least one criterion must have severity "critical"')
    for c in crits:
        try:
            AcceptanceCriterion(**c.model_dump())
        except ValidationError as e:
            msg = e.errors()[0]["msg"].removeprefix("Value error, ")
            found.append(f"{c.id}: {msg}")
    return found


def run_intake(gateway: Gateway, request: str, *, project: Path, limits: Limits,
               request_id: str | None = None) -> IntakeResult:
    request_id = request_id or new_id("task")
    summary = project_summary(project)
    user_msg = f"{summary}\n\n## Request\n\n{request}"
    messages: list[dict] = [{"role": "user", "content": user_msg}]
    invocations: list[ModelInvocation] = []

    for attempt in range(MAX_REPAIRS + 1):
        resp = gateway.call(operation=OPERATION, department=Department.EZRA,
                            system=SYSTEM_PROMPT, messages=messages, max_tokens=MAX_TOKENS,
                            task_id=request_id,
                            context=[("project_summary", summary), ("request", request)],
                            output_format={"type": "json_schema", "schema": SCHEMA})
        invocations.append(resp.invocation)
        if resp.truncated:
            raise IntakeError("intake answer was cut off at the length limit", invocations)
        if not resp.text.strip():
            raise IntakeError("intake returned no text", invocations)
        try:
            decision = IntakeDecision.model_validate(json.loads(resp.text))
            found = problems_with(decision)
        except (json.JSONDecodeError, ValidationError) as e:
            decision, found = None, [f"output didn't match the schema: {e}"]
        if not found:
            break
        gateway.store.log_event(request_id, "intake_invalid", attempt=attempt + 1,
                                problems=found)
        if attempt == MAX_REPAIRS:
            raise IntakeError("intake output was still invalid after a repair: "
                              + "; ".join(found), invocations)
        messages = messages + [
            {"role": "assistant", "content": resp.text},
            {"role": "user", "content": "That intake has problems:\n- " + "\n- ".join(found)
             + "\nReturn the corrected intake."},
        ]

    result = IntakeResult(request_id=request_id, route=decision.route,
                          answer=decision.answer.strip(),
                          unsupported_reason=decision.unsupported_reason.strip(),
                          task_title=decision.task_title.strip(), invocations=invocations)
    if decision.route is Route.CODE:
        if summary == NO_PROJECT:
            raise IntakeError(f"can't create a coding task: no git project at {project}",
                              invocations)
        result.envelope = TaskEnvelope(
            task_id=request_id, target_department=Department.CODE_JOE,
            description=decision.task_description.strip(), project_ref=str(project),
            acceptance_criteria=[AcceptanceCriterion(**c.model_dump())
                                 for c in decision.acceptance_criteria],
            constraints=decision.constraints, counters=LoopCounters.from_limits(limits),
            budget=Budget(task_limit_usd=limits.task_budget_usd,
                          daily_limit_usd=limits.daily_budget_usd))
        gateway.store.save_task(result.envelope)
    gateway.store.log_event(request_id, "intake_routed", route=str(decision.route),
                            title=result.task_title,
                            criteria=len(decision.acceptance_criteria),
                            model_calls=len(invocations))
    return result
