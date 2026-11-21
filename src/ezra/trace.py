"""Task traces (M6): one readable timeline of everything that happened to a task.

Built only from what the store already holds (events, model invocations, Guardian reviews
and approvals), so reading a trace never calls a model and costs nothing. The CLI prints it;
the Phase 2 UI will render the same structure (D-011).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ezra.contracts import (
    ApprovalRecord,
    GuardianReview,
    ModelInvocation,
    TaskEnvelope,
    TaskStatus,
)
from ezra.store import Store

# Which step each model operation belongs to, in plain words.
STEP_OF_OPERATION = {
    "ezra.intake": "intake",
    "code_joe.plan": "plan",
    "builder.implement": "builder",
    "tester.write_tests": "tester",
    "code_joe.adjudicate": "adjudicate",
    "guardian.tier2": "review",
    "learner.reflect": "learner",
}


@dataclass
class TraceRow:
    at: datetime
    step: str
    kind: str  # "model_call" or an event kind
    detail: str
    invocation: ModelInvocation | None = None
    data: dict[str, Any] = field(default_factory=dict)  # the raw event, for friendlier UIs


@dataclass
class OperationTotal:
    operation: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class Trace:
    envelope: TaskEnvelope
    status: TaskStatus
    rows: list[TraceRow]
    totals: list[OperationTotal]
    reviews: list[GuardianReview]
    approvals: list[ApprovalRecord]
    spend_usd: float  # what the budget counts (worst case for calls with no known price)
    unpriced_calls: int
    prompt_versions: dict[str, str] = field(default_factory=dict)  # operation -> version(s)

    @property
    def calls(self) -> int:
        return sum(t.calls for t in self.totals)

    @property
    def verdict(self) -> str | None:
        return str(self.reviews[-1].verdict) if self.reviews else None


def _short(items: Any, n: int = 6) -> str:
    items = list(items or [])
    more = f" +{len(items) - n} more" if len(items) > n else ""
    return ", ".join(str(i) for i in items[:n]) + more


def _event_detail(kind: str, d: dict[str, Any]) -> tuple[str, str]:
    """(step, one-line description) for a non-model event."""
    match kind:
        case "intake_routed":
            return "intake", f"routed {d.get('route')}: {d.get('title', '')} " \
                             f"({d.get('criteria', 0)} criteria)"
        case "intake_invalid":
            return "intake", f"answer broke {len(d.get('problems', []))} rule(s); repairing"
        case "code_joe_started":
            return "setup", f"worktree on {d.get('branch')}, cap ${d.get('task_cap', 0):.2f}"
        case "plan_ready":
            return "plan", f"{d.get('steps')} steps, interface: {_short(d.get('interface'))}"
        case "builder_done":
            return "builder", f"{d.get('turns')} turns, wrote {_short(d.get('files'))}"
        case "tester_done":
            return "tester", f"{d.get('turns')} turns, wrote {_short(d.get('files'))}"
        case "checks_ran":
            ok = "passed" if d.get("passed") else "FAILED"
            extra = f", failing: {_short(d.get('failed'), 3)}" if d.get("failed") else ""
            missing = (f", missing tests: {_short(d.get('missing_tests'))}"
                       if d.get("missing_tests") else "")
            return "checks", f"{ok}: {d.get('cases', 0)} test cases, pytest exit " \
                             f"{d.get('pytest_exit')}, ruff exit {d.get('ruff_exit')}" \
                             f"{extra}{missing}"
        case "adjudicated":
            return "adjudicate", f"fault: {d.get('fault')} (decided by {d.get('by')})"
        case "packaged":
            crit = d.get("criteria") or {}
            met = (f", {sum(v == 'met' for v in crit.values())}/{len(crit)} criteria met "
                   "by checks") if crit else ""
            return "package", f"{d.get('status', 'packaged')}: commit " \
                              f"{str(d.get('commit') or 'none')[:10]}, " \
                              f"{len(d.get('changed_files', []))} files{met}"
        case "reviewed":
            findings = f", findings: {_short(d.get('findings'), 3)}" if d.get("findings") \
                else ""
            return "review", f"{d.get('verdict')} (rule {d.get('rule')}, {d.get('tier')})" \
                             f"{findings}"
        case "revision_started":
            return "revise", f"Guardian sent it back with {len(d.get('corrections', []))} " \
                             "correction(s)"
        case "delivered":
            return "deliver", f"PASS, ready on {d.get('branch')}"
        case "escalated":
            return "escalate", f"ESCALATE: {str(d.get('reason', ''))[:120]}"
        case "code_joe_stopped":
            return "stopped", f"stopped: {_short(d.get('reasons'), 2)}"
        case "budget_hold":
            return STEP_OF_OPERATION.get(d.get("operation", ""), "budget"), \
                f"HOLD {d.get('approval_id')}: worst case ${d.get('worst_case_usd', 0):.4f}"
        case "budget_fit":
            return STEP_OF_OPERATION.get(d.get("operation", ""), "budget"), \
                f"shrunk to fit: max_tokens {d.get('requested_max_tokens')} -> " \
                f"{d.get('max_tokens')}, effort {d.get('effort')}"
        case "hold_answered":
            how = f"approved, +${d.get('extend_usd', 0):.2f}" if d.get("approved") \
                else "rejected"
            return "budget", f"HOLD {d.get('approval_id')} {how}"
        case "run_resumed":
            return "resume", f"resumed from {_short(d.get('from_steps'))} " \
                             f"(was {d.get('status_before')})"
        case "review_requested":
            return "review", f"review requested: {d.get('reason', '')}"
        case "abandoned":
            return "stopped", f"abandoned (was {d.get('status_before')}): {d.get('reason')}"
        case "lessons_injected":
            return "learner", f"gave {len(d.get('lessons', []))} lesson(s) to {d.get('operation')}"
        case "lessons_learned":
            return "learner", (f"learned: +{len(d.get('added', []))} added, "
                               f"{len(d.get('merged', []))} merged, "
                               f"{len(d.get('retired', []))} retired")
        case "lesson_rejected":
            return "learner", f"rejected a lesson: {str(d.get('reason', ''))[:100]}"
        case "unpriced_model":
            return "budget", f"no price for {d.get('model')}; counted at worst case"
    return "other", _short(f"{k}={v}" for k, v in d.items())


def build_trace(store: Store, task_id: str) -> Trace | None:
    found = store.get_task(task_id)
    if found is None:
        return None
    env, status = found
    invocations = {i.invocation_id: i for i in store.invocations_for_task(task_id)}
    rows: list[TraceRow] = []
    seen: set[str] = set()
    for e in store.events_for_task(task_id):
        kind, at = e["kind"], datetime.fromisoformat(e["at"])
        data = {k: v for k, v in e.items() if k not in ("at", "kind")}
        if kind == "model_call_started":
            continue  # the finished row carries everything
        if kind == "model_call_finished":
            inv = invocations.get(data.get("invocation_id", ""))
            if inv is None:
                continue
            seen.add(inv.invocation_id)
            rows.append(TraceRow(at=at, step=STEP_OF_OPERATION.get(inv.operation_id,
                                                                   inv.operation_id),
                                 kind="model_call", detail=_call_detail(inv), invocation=inv))
            continue
        step, detail = _event_detail(kind, data)
        rows.append(TraceRow(at=at, step=step, kind=kind, detail=detail, data=data))
    # Invocations with no finished event (shouldn't happen; kept so nothing is hidden).
    for inv in invocations.values():
        if inv.invocation_id not in seen:
            rows.append(TraceRow(at=inv.created_at, step=STEP_OF_OPERATION.get(
                inv.operation_id, inv.operation_id), kind="model_call",
                detail=_call_detail(inv), invocation=inv))
    rows.sort(key=lambda r: r.at)

    totals: dict[str, OperationTotal] = {}
    versions: dict[str, set[str]] = {}
    unpriced = 0
    for inv in invocations.values():
        t = totals.setdefault(inv.operation_id, OperationTotal(inv.operation_id))
        t.calls += 1
        t.input_tokens += inv.input_tokens
        t.output_tokens += inv.output_tokens
        t.cache_read_tokens += inv.cache_read_tokens
        t.cache_creation_tokens += inv.cache_creation_tokens
        t.latency_ms += inv.latency_ms
        if inv.actual_cost_usd is None:
            unpriced += 1
            t.cost_usd += inv.estimated_cost_usd or 0.0
        else:
            t.cost_usd += inv.actual_cost_usd
        if inv.prompt_version:
            versions.setdefault(inv.operation_id, set()).add(inv.prompt_version)
    order = list(STEP_OF_OPERATION)
    ordered = sorted(totals.values(),
                     key=lambda t: order.index(t.operation) if t.operation in order else 99)
    return Trace(envelope=env, status=status, rows=rows, totals=ordered,
                 reviews=store.reviews_for_task(task_id),
                 approvals=store.approvals_for_task(task_id),
                 spend_usd=store.spend_for_task(task_id), unpriced_calls=unpriced,
                 prompt_versions={k: ", ".join(sorted(v)) for k, v in versions.items()})


def _call_detail(inv: ModelInvocation) -> str:
    model = inv.model_id + (f" (fell back from {inv.requested_model})"
                            if inv.fallback_used else "")
    cost = "cost unknown" if inv.actual_cost_usd is None else f"${inv.actual_cost_usd:.4f}"
    bits = [model, f"in {inv.input_tokens}", f"out {inv.output_tokens}",
            f"cache r/w {inv.cache_read_tokens}/{inv.cache_creation_tokens}", cost,
            f"{inv.latency_ms / 1000:.1f}s"]
    if not inv.success:
        bits.append(f"FAILED: {inv.failure_reason}")
    elif inv.stop_reason not in (None, "end_turn", "tool_use"):
        bits.append(f"stop: {inv.stop_reason}")
    return " · ".join(bits)
