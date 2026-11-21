"""One learning step after a finished task: judge → distill → validate → curate.

    task ends (PASS or ESCALATE)
      → attribution: each lesson the task carried gets a use, and a rating
      → Reflector (one cheap call) proposes ≤3 lessons, unless the run was clean
      → deterministic validation (leakage, vagueness)
      → Curator applies small deltas (add, merge, retire)
      → next task: retrieval puts the relevant few into the prompts

Learning never asks for money. The Reflector's call goes through the Gateway like every
other call, under the task's own caps; if it wouldn't fit (the Gateway would HOLD), the
reflection is skipped and logged instead of pausing a task that's already delivered. A
failed reflection never changes the task's outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ezra.config import LearningConfig
from ezra.contracts import LessonStatus, TaskStatus, Verdict
from ezra.gateway import BudgetHold, GatewayError
from ezra.learner.curator import CurationReport, apply_proposals, apply_ratings
from ezra.learner.reflector import ReflectorError, reflect
from ezra.learner.retrieval import project_name
from ezra.learner.validator import validate
from ezra.store import Store

FINISHED = (TaskStatus.DONE, TaskStatus.ESCALATED)


@dataclass
class LearnOutcome:
    task_id: str
    skipped: str | None = None  # why nothing was learned, if so
    reflected: bool = False
    added: list[str] = field(default_factory=list)
    merged: list[str] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)  # validator reasons
    rated: dict[str, str] = field(default_factory=dict)
    cost_usd: float = 0.0


def is_clean(store: Store, task_id: str) -> bool:
    """First review PASSed with no findings and the checks never failed: nothing to learn.
    (A guess to save tokens: ReasoningBank also learns from successes. Worth testing.)"""
    reviews = store.reviews_for_task(task_id)
    if len(reviews) != 1 or reviews[0].verdict is not Verdict.PASS or reviews[0].findings:
        return False
    return all(e.get("passed") for e in store.events_for_task(task_id)
               if e["kind"] == "checks_ran")


def learn_from_task(store: Store, gateway: Any, task_id: str,
                    config: LearningConfig) -> LearnOutcome:
    out = LearnOutcome(task_id=task_id)
    found = store.get_task(task_id)
    if found is None:
        out.skipped = "no such task"
        return out
    env, status = found
    if status not in FINISHED:
        out.skipped = f"task is {status}; only finished tasks teach lessons"
        return out
    if store.has_event(task_id, "lessons_learned"):
        out.skipped = "already learned from this task"
        return out
    if not store.reviews_for_task(task_id):
        out.skipped = "no Guardian review to learn from"
        return out

    used = store.lessons_used_by_task(task_id)
    report = CurationReport()
    ratings: dict[str, str] = {}
    project = project_name(env.project_ref)
    if is_clean(store, task_id):
        # Credit by association: the run went cleanly with these lessons in the prompts.
        ratings = dict.fromkeys(used, "helpful")
        out.skipped = "clean run: nothing new to learn"
    else:
        used_lessons = [lsn for lid in used if (lsn := store.get_lesson(lid))]
        existing = [lsn for op in config.inject_into
                    for lsn in store.lessons(LessonStatus.ACTIVE, op)
                    if lsn.project in (None, project)]
        try:
            refl = reflect(lambda **kw: gateway.call(
                **kw, task_budget_usd=env.budget.task_limit_usd,
                daily_budget_usd=env.budget.daily_limit_usd, persist_hold=False),
                store, env, used_lessons, existing)
        except BudgetHold as hold:
            out.skipped = f"reflection skipped to stay in budget: {hold.approval.summary}"
        except (GatewayError, ReflectorError) as e:
            out.skipped = f"reflection failed: {e}"
            invs = e.invocations if isinstance(e, ReflectorError) else [e.invocation]
            out.cost_usd = sum(i.actual_cost_usd or 0.0 for i in invs)
        else:
            out.reflected = True
            out.cost_usd = sum(i.actual_cost_usd or 0.0 for i in refl.invocations)
            ratings = refl.ratings
            valid = []
            for p in refl.lessons:
                check = validate(p, env, config.inject_into)
                if check.ok:
                    valid.append(p)
                else:
                    out.rejected.append(f"{p.operation}: {check.reason}")
                    store.log_event(task_id, "lesson_rejected", operation=p.operation,
                                    reason=check.reason, text=p.text[:300])
            apply_proposals(store, valid, task_id, project, config, report)

    apply_ratings(store, used, ratings, task_id, config, report)
    out.added, out.merged, out.retired, out.rated = (report.added, report.merged,
                                                     report.retired, report.rated)
    store.log_event(task_id, "lessons_learned", reflected=out.reflected, added=out.added,
                    merged=out.merged, retired=out.retired, rejected=len(out.rejected),
                    rated=out.rated, skipped=out.skipped, cost_usd=round(out.cost_usd, 6),
                    config_version=config.version)
    return out
