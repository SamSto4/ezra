"""The Curator: deterministic code, not a model, that edits the playbook by small deltas.

Following ACE, the playbook is never rewritten as a whole (that erodes detail over time,
"context collapse"). Each change is one of:
- ADD     a new lesson (inferred lessons go live at once and you're told: D-009 Level 2);
- MERGE   a near-duplicate into the lesson it restates: its evidence grows, its text stays;
- RATE    bump uses, helpful or harmful after a task that carried the lesson;
- RETIRE  when harmful passes helpful by the configured margin, when the operation has too
          many active lessons (the lowest-ranked goes), or when you retire it by hand.
Every change is a new version in lesson_history, so the playbook's past is never lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ezra.config import LearningConfig
from ezra.contracts import Lesson, LessonKind, LessonStatus, utcnow
from ezra.learner.reflector import ProposedLesson
from ezra.store import Store

_WORD = re.compile(r"[a-z0-9_]+")
_STOP = frozenset("a an the and or of to in on for with is are be it its this that when "
                  "if as by at from so not no do does than then".split())


def words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def similarity(a: str, b: str) -> float:
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


@dataclass
class CurationReport:
    added: list[str] = field(default_factory=list)
    merged: list[str] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)
    rated: dict[str, str] = field(default_factory=dict)


def _bump(lesson: Lesson, **changes) -> Lesson:
    return lesson.model_copy(update={**changes, "version": lesson.version + 1,
                                     "updated_at": utcnow()})


def _find_duplicate(store: Store, p: ProposedLesson, project: str | None,
                    threshold: float) -> Lesson | None:
    active = [lsn for lsn in store.lessons(LessonStatus.ACTIVE, p.operation)
              if lsn.project in (None, project)]
    if p.merge_with:
        named = next((lsn for lsn in active if lsn.lesson_id == p.merge_with), None)
        if named is not None:
            return named
    text = f"{p.trigger} {p.text}"
    best = max(active, key=lambda lsn: similarity(text, f"{lsn.trigger} {lsn.text}"),
               default=None)
    if best is not None and similarity(text, f"{best.trigger} {best.text}") >= threshold:
        return best
    return None


def apply_proposals(store: Store, proposals: list[ProposedLesson], task_id: str,
                    project: str | None, config: LearningConfig,
                    report: CurationReport) -> None:
    for p in proposals[:config.max_lessons_per_task]:
        dup = _find_duplicate(store, p, project, config.merge_similarity)
        if dup is not None:
            if task_id in dup.evidence:
                continue
            store.save_lesson(_bump(dup, evidence=[*dup.evidence, task_id]), "merged",
                              task_id, reason=f"restated: {p.text[:200]}")
            report.merged.append(dup.lesson_id)
            continue
        lesson = Lesson(operation=p.operation, project=project, kind=LessonKind(p.kind),
                        trigger=p.trigger.strip(), text=p.text.strip(), evidence=[task_id])
        store.save_lesson(lesson, "added", task_id, reason="distilled from Guardian outcome")
        report.added.append(lesson.lesson_id)
        _enforce_cap(store, p.operation, config, task_id, report, keep=lesson.lesson_id)


def _enforce_cap(store: Store, operation: str, config: LearningConfig, task_id: str,
                 report: CurationReport, keep: str) -> None:
    active = store.lessons(LessonStatus.ACTIVE, operation)
    excess = len(active) - config.max_active_per_operation
    if excess <= 0:
        return
    # Lowest score first, then least reinforced, then oldest. The lesson just added is
    # spared: it hasn't had a chance to prove itself yet.
    ranked = sorted((lsn for lsn in active if lsn.lesson_id != keep),
                    key=lambda lsn: (lsn.score, len(lsn.evidence), lsn.updated_at))
    for lsn in ranked[:excess]:
        retire(store, lsn, f"over the cap of {config.max_active_per_operation} "
                           f"active lessons for {operation}", task_id)
        report.retired.append(lsn.lesson_id)


def apply_ratings(store: Store, used: list[str], ratings: dict[str, str], task_id: str,
                  config: LearningConfig, report: CurationReport) -> None:
    """Every lesson the task carried gets one more use; rated ones move their counters."""
    for lesson_id in used:
        lsn = store.get_lesson(lesson_id)
        if lsn is None:
            continue
        rating = ratings.get(lesson_id, "neutral")
        lsn = _bump(lsn, uses=lsn.uses + 1,
                    helpful=lsn.helpful + (rating == "helpful"),
                    harmful=lsn.harmful + (rating == "harmful"))
        store.save_lesson(lsn, "rated", task_id, reason=rating)
        report.rated[lesson_id] = rating
        if lsn.status is LessonStatus.ACTIVE and lsn.harmful - lsn.helpful >= config.retire_margin:
            retire(store, lsn, f"harmful {lsn.harmful} vs helpful {lsn.helpful}", task_id)
            report.retired.append(lesson_id)


def retire(store: Store, lesson: Lesson, reason: str, task_id: str | None = None) -> Lesson:
    retired = _bump(lesson, status=LessonStatus.RETIRED)
    store.save_lesson(retired, "retired", task_id, reason=reason)
    return retired
