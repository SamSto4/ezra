"""Ezra's core actions. Every interface (the CLI now, the UI later; D-011) calls these
functions and only formats what they return. No interface holds logic of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ezra.config import DATA_DIR, load_limits, load_routing
from ezra.contracts import ApprovalRecord, Department, ModelInvocation
from ezra.gateway import Gateway
from ezra.pricing import load_pricing
from ezra.store import Store

DB_PATH = DATA_DIR / "ezra.db"

# M2 answers questions directly. M3 turns this call into the structured intake
# (route + Acceptance Criteria) on the same `ezra.intake` operation.
ASK_SYSTEM = (
    "You are Ezra, a personal AI assistant. Answer the user's question directly and "
    "concisely. If you don't know something, say so."
)
ASK_MAX_TOKENS = 4096


@dataclass
class AskResult:
    text: str
    truncated: bool
    invocation: ModelInvocation


def open_store(db_path: Path | str = DB_PATH) -> Store:
    return Store(db_path)


def open_gateway(store: Store, client: Any = None) -> Gateway:
    return Gateway(store=store, routing=load_routing(), limits=load_limits(),
                   pricing=load_pricing(), client=client)


def ask(gateway: Gateway, question: str) -> AskResult:
    resp = gateway.call(operation="ezra.intake", department=Department.EZRA,
                        system=ASK_SYSTEM, messages=[{"role": "user", "content": question}],
                        max_tokens=ASK_MAX_TOKENS)
    return AskResult(text=resp.text, truncated=resp.truncated, invocation=resp.invocation)


def pending_approvals(store: Store) -> list[ApprovalRecord]:
    return store.pending_approvals()
