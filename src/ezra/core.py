"""Ezra's core actions. Every interface (the CLI now, the UI later; D-011) calls these
functions and only formats what they return. No interface holds logic of its own.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from ezra.code_joe.graph import Context, build_graph
from ezra.config import DATA_DIR, PLAYGROUND_DIR, load_limits, load_routing
from ezra.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    GuardianReview,
    StandardDepartmentResult,
    TaskEnvelope,
    TaskStatus,
)
from ezra.gateway import Gateway
from ezra.intake import IntakeResult, run_intake
from ezra.pricing import load_pricing
from ezra.store import Store

DB_PATH = DATA_DIR / "ezra.db"
CHECKPOINT_PATH = DATA_DIR / "checkpoints.db"
WORKTREES_DIR = DATA_DIR / "worktrees"


def open_store(db_path: Path | str = DB_PATH) -> Store:
    return Store(db_path)


def open_gateway(store: Store, client: Any = None) -> Gateway:
    return Gateway(store=store, routing=load_routing(), limits=load_limits(),
                   pricing=load_pricing(), client=client)


def ask(gateway: Gateway, request: str, project: Path = PLAYGROUND_DIR) -> IntakeResult:
    """Route a request: answer it, turn it into a task for Code Joe, or explain why not."""
    return run_intake(gateway, request, project=project, limits=gateway.limits)


@dataclass
class TaskView:
    envelope: TaskEnvelope
    status: TaskStatus
    spend_usd: float
    events: list[dict[str, Any]]
    reviews: list[GuardianReview]


def get_task(store: Store, task_id: str) -> TaskView | None:
    found = store.get_task(task_id)
    if found is None:
        return None
    envelope, status = found
    return TaskView(envelope=envelope, status=status, spend_usd=store.spend_for_task(task_id),
                    events=store.events_for_task(task_id),
                    reviews=store.reviews_for_task(task_id))


def pending_approvals(store: Store) -> list[ApprovalRecord]:
    return store.pending_approvals()


# -- Code Joe (M4) -----------------------------------------------------------------------


class RunError(Exception):
    pass


@dataclass
class RunOutcome:
    task_id: str
    status: TaskStatus
    outcome: str  # "passed", "escalated", "stopped" or "held"
    holds: list[dict[str, Any]]  # pending HOLDs: approval_id, node, summary
    result: StandardDepartmentResult | None
    review: GuardianReview | None  # the last Guardian review
    reviews: int  # how many reviews the task got (1, or 2 after a REVISE)
    stopped: list[str]
    spend_usd: float


def _graph(store: Store, gateway: Gateway, checkpoint_path: Path | str,
           worktrees_dir: Path | None):
    Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(checkpoint_path), check_same_thread=False)
    ctx = Context(store=store, gateway=gateway, worktrees_dir=worktrees_dir or WORKTREES_DIR,
                  test_timeout=gateway.limits.test_timeout_seconds)
    return build_graph(ctx, SqliteSaver(conn)), conn


def _outcome(store: Store, app: Any, cfg: dict, task_id: str) -> RunOutcome:
    snap = app.get_state(cfg)
    values = snap.values
    holds = [i.value for i in snap.interrupts]
    result = values.get("result")
    review = values.get("review")
    return RunOutcome(
        task_id=task_id, status=store.get_task(task_id)[1],
        outcome="held" if holds else values.get("outcome", "stopped"), holds=holds,
        result=StandardDepartmentResult.model_validate(result) if result else None,
        review=GuardianReview.model_validate(review) if review else None,
        reviews=len(store.reviews_for_task(task_id)),
        stopped=values.get("stopped", []), spend_usd=store.spend_for_task(task_id))


def _drive(app: Any, payload: Any, cfg: dict, on_step: Any) -> None:
    for chunk in app.stream(payload, cfg, stream_mode="updates"):
        for node in chunk:
            if on_step and not node.startswith("__"):
                on_step(node)


def run_task(store: Store, gateway: Gateway, task_id: str,
             task_budget_usd: float | None = None,
             checkpoint_path: Path | str = CHECKPOINT_PATH,
             worktrees_dir: Path | None = None, on_step: Any = None) -> RunOutcome:
    """Run Code Joe on a created task. `task_budget_usd` can only lower the cap for this run;
    raising it is the user's decision (an approved HOLD)."""
    found = store.get_task(task_id)
    if found is None:
        raise RunError(f"No task '{task_id}'.")
    env, status = found
    if status is not TaskStatus.CREATED:
        raise RunError(f"Task {task_id} is {status}; only created tasks can be run.")
    cap = env.budget.task_limit_usd
    if task_budget_usd is not None:
        if task_budget_usd > cap:
            raise RunError(f"--task-budget can only lower the cap (max ${cap:.2f}).")
        cap = task_budget_usd
    app, conn = _graph(store, gateway, checkpoint_path, worktrees_dir)
    cfg = {"configurable": {"thread_id": task_id}}
    try:
        _drive(app, {"task_id": task_id, "task_cap": cap,
                     "daily_cap": env.budget.daily_limit_usd, "budget_extra_task": 0.0,
                     "budget_extra_day": 0.0}, cfg, on_step)
        return _outcome(store, app, cfg, task_id)
    finally:
        conn.close()


def default_extension(approval: ApprovalRecord) -> float:
    """Just enough to let the held call through, rounded up to 5 cents."""
    d = approval.details
    short = [0.0]
    if "task" in d.get("breaches", ["task"]):
        short.append(d["spent_task_usd"] + d["worst_case_usd"] - d["task_budget_usd"])
    if "daily" in d.get("breaches", []):
        short.append(d["spent_today_usd"] + d["worst_case_usd"] - d["daily_budget_usd"])
    return math.ceil(max(short) * 20 + 1e-9) / 20


def answer_hold(store: Store, gateway: Gateway, approval_id: str, approved: bool,
                extend_usd: float | None = None, note: str | None = None,
                checkpoint_path: Path | str = CHECKPOINT_PATH,
                worktrees_dir: Path | None = None, on_step: Any = None) -> RunOutcome:
    """Approve or reject a HOLD and resume the paused task (D-009 Level 1)."""
    approval = store.get_approval(approval_id)
    if approval is None:
        raise RunError(f"No approval '{approval_id}'.")
    if approval.status is not ApprovalStatus.PENDING:
        raise RunError(f"Approval {approval_id} is already {approval.status}.")
    if approval.task_id is None or store.get_task(approval.task_id) is None:
        # A HOLD from `ezra ask`: nothing to resume, just record the answer.
        store.resolve_approval(approval_id, approved, note)
        raise RunError("That HOLD came from `ezra ask`; there's no task to resume. "
                       "Run the request again.")
    extend = default_extension(approval) if extend_usd is None else extend_usd
    app, conn = _graph(store, gateway, checkpoint_path, worktrees_dir)
    cfg = {"configurable": {"thread_id": approval.task_id}}
    try:
        snap = app.get_state(cfg)
        match = [i for i in snap.interrupts if i.value.get("approval_id") == approval_id]
        if not match:
            raise RunError(f"Task {approval.task_id} isn't paused on {approval_id}.")
        store.resolve_approval(approval_id, approved,
                               note or (f"extend ${extend:.2f}" if approved else "rejected"),
                               extra_details={"extend_usd": extend if approved else 0.0})
        store.log_event(approval.task_id, "hold_answered", approval_id=approval_id,
                        approved=approved, extend_usd=extend if approved else 0.0)
        _drive(app, Command(resume={match[0].id: {"approved": approved,
                                                  "extend_usd": extend}}), cfg, on_step)
        return _outcome(store, app, cfg, approval.task_id)
    finally:
        conn.close()
