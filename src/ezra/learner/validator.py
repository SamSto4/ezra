"""Deterministic checks on a proposed lesson, before it can reach any prompt.

A wrong lesson is worse than none: it's re-injected into every later task. These rules
are cheap and certain. They catch the two known failure modes of learned memory:
- leakage: a lesson that carries this task's answers (test values, criterion ids, the
  acceptance test file) instead of a reusable idea;
- brevity bias: vague advice like "write good code" that costs tokens and helps nobody.

The research plan also has Guardian validate lessons (a model check for contradictions
with active lessons and Standards). That's a change to Guardian's job, so it waits for the
user's yes (D-009 Level 1). Until then, these checks are the only gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ezra.contracts import TaskEnvelope
from ezra.learner.reflector import ProposedLesson

TEXT_CHARS = (25, 320)
TRIGGER_CHARS = (5, 200)
MIN_SPECIFIC_WORDS = 12

_IDS = re.compile(r"\b(AC\d+|task_[0-9a-f]{6,}|les_[0-9a-f]{6,})\b", re.IGNORECASE)
_ACCEPTANCE_PATH = re.compile(r"tests/acceptance/", re.IGNORECASE)
_QUOTED = re.compile(r"""(?:"([^"\n]+)"|(?<!\w)'([^'\n]+)'(?!\w)|`([^`\n]+)`)""")
_NUMBER = re.compile(r"(?<![\w.])-?\d{2,}(?:\.\d+)?(?![\w.])")
_VAGUE = re.compile(
    r"\b(best practices?|be careful|clean code|good code|high[- ]quality|pay attention|"
    r"double[- ]check everything|make sure (it|the code|everything) works|think carefully)\b",
    re.IGNORECASE)


@dataclass
class Check:
    ok: bool
    reason: str = ""


def task_literals(env: TaskEnvelope) -> set[str]:
    """Values a lesson must not carry: quoted strings and multi-digit numbers from the task
    and its criteria. Identifiers (function names) aren't listed here; the Reflector is told
    to avoid them, and project scoping limits the harm if one slips through."""
    text = " ".join([env.description, *(c.text for c in env.acceptance_criteria)])
    found = {next(g for g in m.groups() if g).strip().lower() for m in _QUOTED.finditer(text)}
    found = {f for f in found if len(f) >= 3}
    return found | set(_NUMBER.findall(text))


def validate(proposal: ProposedLesson, env: TaskEnvelope, allowed_operations: list[str]
             ) -> Check:
    text, trigger = proposal.text.strip(), proposal.trigger.strip()
    both = f"{trigger} {text}"
    if proposal.operation not in allowed_operations:
        return Check(False, f"operation {proposal.operation} doesn't receive lessons")
    if not TEXT_CHARS[0] <= len(text) <= TEXT_CHARS[1]:
        return Check(False, f"text must be {TEXT_CHARS[0]}-{TEXT_CHARS[1]} characters")
    if not TRIGGER_CHARS[0] <= len(trigger) <= TRIGGER_CHARS[1]:
        return Check(False, f"trigger must be {TRIGGER_CHARS[0]}-{TRIGGER_CHARS[1]} characters")
    if m := _IDS.search(both):
        return Check(False, f"leakage: names a specific id ({m.group(0)})")
    if _ACCEPTANCE_PATH.search(both):
        return Check(False, "leakage: names the acceptance test files")
    lowered = both.lower()
    for lit in sorted(task_literals(env)):
        if re.search(rf"(?<![\w.]){re.escape(lit)}(?![\w.])", lowered):
            return Check(False, f"leakage: repeats the task's value '{lit}'")
    if _VAGUE.search(both) and len(both.split()) < MIN_SPECIFIC_WORDS:
        return Check(False, "too vague to act on")
    return Check(True)
