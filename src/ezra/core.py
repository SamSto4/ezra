"""Ezra's core actions. Every interface (the CLI now, the UI later; D-011) calls these
functions and only formats what they return. No interface holds logic of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ezra.config import DATA_DIR, PLAYGROUND_DIR, load_limits, load_routing
from ezra.contracts import ApprovalRecord, TaskEnvelope, TaskStatus
from ezra.gateway import Gateway
from ezra.intake import IntakeResult, run_intake
from ezra.pricing import load_pricing
from ezra.store import Store

DB_PATH = DATA_DIR / "ezra.db"


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


def get_task(store: Store, task_id: str) -> TaskView | None:
    found = store.get_task(task_id)
    if found is None:
        return None
    envelope, status = found
    return TaskView(envelope=envelope, status=status, spend_usd=store.spend_for_task(task_id),
                    events=store.events_for_task(task_id))


def pending_approvals(store: Store) -> list[ApprovalRecord]:
    return store.pending_approvals()
