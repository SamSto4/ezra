"""Retrieve the few relevant lessons for one prompt, within a token cap.

Every injected token is paid for on every call that carries it, so retrieval is strict:
1. filter: active lessons for this operation, for this project or for any project;
2. rank: helpful minus harmful, then how often it was reinforced, then confirmed before
   inferred, then newest;
3. cut at the token cap (estimated at 4 characters per token, a guess the Gateway's real
   count then checks against the budget);
4. render in a fixed order (by id), so the same set gives byte-identical text and the
   block rides the prompt cache across turns and tasks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from ezra.config import LearningConfig
from ezra.contracts import Lesson, LessonSource, LessonStatus
from ezra.store import Store

HEADER = (
    "## Lessons from earlier tasks\n"
    "Ezra learned these from Guardian's reviews of past work. Apply a lesson only when its "
    "trigger matches this task. The task, its Acceptance Criteria and the rules above always "
    "win over a lesson.\n")


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def lesson_line(lesson: Lesson) -> str:
    return f"- [{lesson.lesson_id}] ({lesson.kind}) When {lesson.trigger.rstrip('.')}: " \
           f"{lesson.text}"


def project_name(project_ref: str | None) -> str | None:
    return Path(project_ref).name if project_ref else None


def _rank_key(lesson: Lesson) -> tuple:
    return (-lesson.score, -len(lesson.evidence), lesson.source is not LessonSource.CONFIRMED,
            -lesson.updated_at.timestamp(), lesson.lesson_id)


def select_lessons(store: Store, operation: str, project: str | None,
                   token_cap: int) -> list[Lesson]:
    candidates = [lsn for lsn in store.lessons(LessonStatus.ACTIVE, operation)
                  if lsn.project in (None, project)]
    chosen, used = [], estimate_tokens(HEADER)
    for lesson in sorted(candidates, key=_rank_key):
        cost = estimate_tokens(lesson_line(lesson)) + 1
        if used + cost > token_cap:
            continue  # a shorter, lower-ranked lesson may still fit
        chosen.append(lesson)
        used += cost
    return sorted(chosen, key=lambda lsn: lsn.lesson_id)


def render(lessons: list[Lesson]) -> str:
    return HEADER + "\n".join(lesson_line(lsn) for lsn in lessons) if lessons else ""


@dataclass
class LessonProvider:
    """Gives each injectable call its lesson block, and records which lessons a task used.

    The choice is made once per task and operation and then reused, so every turn of an
    agent loop sends the same block (cache hits) and attribution is exact."""

    store: Store
    config: LearningConfig
    _chosen: dict[tuple[str, str], tuple[str, list[str]]] = field(default_factory=dict)

    def for_call(self, task_id: str | None, operation: str) -> tuple[str, list[str]]:
        if task_id is None or operation not in self.config.inject_into:
            return "", []
        key = (task_id, operation)
        if key not in self._chosen:
            found = self.store.get_task(task_id)
            project = project_name(found[0].project_ref) if found else None
            lessons = select_lessons(self.store, operation, project,
                                     self.config.retrieval_token_cap)
            for lsn in lessons:
                self.store.record_lesson_use(task_id, lsn.lesson_id, operation)
            ids = [lsn.lesson_id for lsn in lessons]
            if ids:
                self.store.log_event(task_id, "lessons_injected", operation=operation,
                                     lessons=ids, est_tokens=estimate_tokens(render(lessons)))
            self._chosen[key] = (render(lessons), ids)
        return self._chosen[key]
