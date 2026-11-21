"""The Reflector: distills a judged outcome into at most three short lessons.

It reads the *structured* outcome Ezra already logged (checks, adjudications, Guardian's
verdicts, findings and corrections), never a transcript. That keeps the call small and
means every lesson traces back to something Guardian or the tests actually saw.

It also rates the lessons that were in this task's prompts (helpful, harmful or neutral),
which is how a lesson's counters move (ACE-style feedback). The rating is a model's
judgment, so it's only ever one vote; retirement needs a margin (config/learning.yaml).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from ezra.code_joe.agents import _schema, criteria_text
from ezra.contracts import Department, Lesson, ModelInvocation, TaskEnvelope
from ezra.learner.retrieval import lesson_line
from ezra.store import Store

OPERATION = "learner.reflect"
MAX_TOKENS = 3_000
DIGEST_CHARS = 12_000

Operation = Literal["code_joe.plan", "builder.implement", "tester.write_tests"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposedLesson(_M):
    operation: Operation
    kind: Literal["strategy", "pitfall", "check"]
    trigger: str
    text: str
    merge_with: str  # an existing lesson id it restates, or "" for a new lesson


class LessonRating(_M):
    lesson_id: str
    rating: Literal["helpful", "harmful", "neutral"]
    reason: str


class ReflectorAnswer(_M):
    lessons: list[ProposedLesson]
    ratings: list[LessonRating]


SCHEMA = _schema(ReflectorAnswer)

SYSTEM = """\
You are the Reflector in Ezra, a personal AI agent. Ezra's coding department just finished
a task and its independent reviewer, Guardian, judged it. Your job is to turn what went
wrong (or notably right) into short lessons that make the NEXT, different task go better.

Who gets lessons:
- "code_joe.plan": the planner, who writes the steps and the interface spec (signatures)
  that Builder and Tester share.
- "builder.implement": Builder, who writes the code without seeing the acceptance tests.
- "tester.write_tests": Tester, who writes acceptance tests from the criteria and the
  interface spec, without seeing the code.

1. lessons: zero to three. A good lesson:
   - generalizes beyond this task. Never include this task's test values, expected outputs,
     criterion ids, file names or function names. Describe the class of problem instead
     ("when a criterion names an edge case like empty input, handle it explicitly").
   - is specific enough to act on. "Write good code" or "be careful" are useless.
   - has a trigger (when it applies) and a text (what to do), one or two sentences each.
   - goes to the role that made the mistake. If Guardian's correction was about the code,
     that's Builder; a wrong signature in the spec is the planner; a test that checked
     something the criteria don't say is Tester.
   - kind: "pitfall" (a mistake to avoid), "check" (something to verify before finishing)
     or "strategy" (an approach that worked).
   If an existing lesson already says it, set merge_with to that lesson's id and restate it
   briefly; otherwise leave merge_with empty. If the task went cleanly and there's nothing
   new, return no lessons. An empty list is a good answer.

2. ratings: one for each lesson listed under "Lessons in this task's prompts", and only
   those. "helpful" if the outcome shows it was followed and it mattered, "harmful" if
   following it caused a problem Guardian or the tests caught, otherwise "neutral". Give a
   one-sentence reason.
"""


class ReflectorError(Exception):
    def __init__(self, message: str, invocations: list[ModelInvocation]):
        super().__init__(message)
        self.invocations = invocations


@dataclass
class Reflection:
    lessons: list[ProposedLesson]
    ratings: dict[str, str]  # lesson_id -> helpful | harmful | neutral
    invocations: list[ModelInvocation]


def outcome_digest(store: Store, env: TaskEnvelope) -> str:
    """What happened, in order, from the structured records only."""
    lines: list[str] = []
    for e in store.events_for_task(env.task_id):
        kind = e["kind"]
        if kind == "checks_ran":
            status = "passed" if e.get("passed") else "FAILED"
            detail = []
            if e.get("failed"):
                detail.append("failing: " + ", ".join(e["failed"][:8]))
            if e.get("missing_tests"):
                detail.append("criteria without tests: " + ", ".join(e["missing_tests"]))
            if e.get("ruff_exit") not in (0, None):
                detail.append("lint problems")
            lines.append(f"- Checks {status}" + (f" ({'; '.join(detail)})" if detail else ""))
        elif kind == "adjudicated":
            lines.append(f"- Failure judged: fault={e.get('fault')} ({e.get('reason', '')})")
        elif kind == "revision_started":
            lines.append("- Guardian sent the work back (REVISE); Builder got the corrections")
        elif kind in ("delivered", "escalated"):
            lines.append(f"- Final outcome: {kind}")
    for i, rev in enumerate(store.reviews_for_task(env.task_id), 1):
        lines.append(f"\n### Guardian review {i}: {rev.verdict} (rule {rev.matched_rule})")
        if rev.summary:
            lines.append(f"Summary: {rev.summary}")
        for c in rev.criteria_results:
            if c.status != "met":
                lines.append(f"- {c.criterion_id} {c.status}: {c.evidence}")
        for f in rev.findings:
            lines.append(f"- finding [{f.severity}] {f.code}: {f.message}")
        for c in rev.required_corrections:
            lines.append(f"- correction: {c}")
    text = "\n".join(lines)
    return text if len(text) <= DIGEST_CHARS else text[:DIGEST_CHARS] + "\n…(cut)"


def reflect(call: Callable[..., Any], store: Store, env: TaskEnvelope, used: list[Lesson],
            existing: list[Lesson]) -> Reflection:
    used_text = "\n".join(lesson_line(lsn) for lsn in used) or "- none"
    existing_text = "\n".join(f"{lesson_line(lsn)} [for {lsn.operation}]"
                              for lsn in existing) or "- none"
    user = (f"## Task\n{env.description}\n\n## Acceptance criteria\n"
            f"{criteria_text(env.acceptance_criteria)}\n\n## What happened\n"
            f"{outcome_digest(store, env)}\n\n## Lessons in this task's prompts\n{used_text}"
            f"\n\n## Existing lessons\n{existing_text}")
    resp = call(operation=OPERATION, department=Department.LEARNER, system=SYSTEM,
                messages=[{"role": "user", "content": user}], max_tokens=MAX_TOKENS,
                task_id=env.task_id, output_format={"type": "json_schema", "schema": SCHEMA})
    invs = [resp.invocation]
    if resp.truncated or not resp.text.strip():
        raise ReflectorError("the reflection was cut off or empty", invs)
    try:
        answer = ReflectorAnswer.model_validate_json(resp.text)
    except ValidationError as e:
        raise ReflectorError(f"the reflection didn't match its schema: {e}", invs) from e
    used_ids = {lsn.lesson_id for lsn in used}
    ratings = {r.lesson_id: r.rating for r in answer.ratings if r.lesson_id in used_ids}
    return Reflection(lessons=answer.lessons, ratings=ratings, invocations=invs)
