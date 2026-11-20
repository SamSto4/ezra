"""The Model Gateway: the only place in Ezra that calls Claude.

Every call goes through `Gateway.call()`, which:
1. looks up the model and effort for the operation (config/routing.yaml),
2. checks the budget *before* spending: spend so far + this call's worst case (D-009 Level 1),
   and on a breach stores a pending approval and raises BudgetHold without calling the model,
3. sends the request with adaptive thinking, effort, system-prompt caching and server-side
   refusal fallbacks, letting the SDK do the bounded infrastructure retries (D-004),
4. writes exactly one ModelInvocation row (success or failure) plus start/finish events.

Nothing here ever logs the API key or the raw request.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import anthropic

from ezra.config import RoutingTable
from ezra.contracts import ApprovalRecord, Department, Limits, ModelInvocation
from ezra.pricing import PriceTable
from ezra.store import Store

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class GatewayError(Exception):
    """The call failed after the SDK's retries. The invocation row is already written."""

    def __init__(self, message: str, invocation: ModelInvocation):
        super().__init__(message)
        self.invocation = invocation


class ModelRefusal(GatewayError):
    """Claude (and its fallback) declined the request."""


class MissingCredentials(Exception):
    """No API key, auth token or `ant auth login` profile was found."""


class BudgetHold(Exception):
    """D-009 Level 1: this call would pass a budget limit. Nothing was sent to the model."""

    def __init__(self, approval: ApprovalRecord):
        super().__init__(approval.summary)
        self.approval = approval


@dataclass
class GatewayResponse:
    text: str
    stop_reason: str | None
    truncated: bool  # hit max_tokens; the caller decides whether that's acceptable
    invocation: ModelInvocation
    message: Any  # the SDK message, for callers that need structured content


def start_of_local_day(now: datetime) -> datetime:
    local = now.astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


class Gateway:
    def __init__(self, *, store: Store, routing: RoutingTable, limits: Limits,
                 pricing: PriceTable, client: Any = None,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        # Fail fast: every routed model (and its fallbacks) must have a price.
        for route in routing.operations.values():
            pricing.require(route.model)
        self.store, self.routing, self.limits, self.pricing = store, routing, limits, pricing
        self.now = now
        # The SDK retries connection errors, 408/409/429 and 5xx with backoff. That is
        # D-004's infra_retries; we don't add a second retry loop on top.
        if client is None:
            client = anthropic.Anthropic(max_retries=limits.max_infra_retries)
            if not (client.api_key or client.auth_token or client.credentials):
                raise MissingCredentials(
                    "No Claude credentials found. Set ANTHROPIC_API_KEY in ~/.zshrc "
                    "(then open a new terminal) or run `ant auth login`.")
        self.client = client

    # -- public -------------------------------------------------------------

    def call(self, *, operation: str, department: Department, system: str,
             messages: list[dict[str, Any]], max_tokens: int, task_id: str | None = None,
             output_format: dict[str, Any] | None = None) -> GatewayResponse:
        route = self.routing.route(operation)
        output_config: dict[str, Any] = {"effort": route.effort}
        if output_format is not None:
            output_config["format"] = output_format
        # Static system prompt marked for caching. Prompts under the model's minimum
        # (512 tokens) simply don't cache; that costs nothing extra.
        system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        shared = dict(model=route.model, system=system_blocks, messages=messages,
                      thinking={"type": "adaptive"}, output_config=output_config,
                      betas=[FALLBACK_BETA])

        input_tokens = self._count_input(shared)
        worst = self.pricing.worst_case(route.model, input_tokens=input_tokens,
                                        max_tokens=max_tokens)
        self._check_budget(task_id=task_id, operation=operation, model=route.model, worst=worst)

        self.store.log_event(task_id, "model_call_started", operation=operation,
                             department=str(department), model=route.model,
                             effort=route.effort, counted_input_tokens=input_tokens,
                             max_tokens=max_tokens, worst_case_usd=round(worst, 6))
        base = dict(task_id=task_id, operation_id=operation, department=department,
                    operation_type=operation.split(".", 1)[-1], requested_model=route.model,
                    routing_policy_version=self.routing.version, estimated_cost_usd=worst)
        started = time.monotonic()
        message, request_id = None, None
        try:
            message, request_id = self._send(dict(shared, max_tokens=max_tokens,
                                                  fallbacks="default"))
        except BaseException as exc:  # record every failure, then re-raise
            # The API answered with an error status (4xx/5xx): nothing was generated or
            # billed, so book $0. Timeouts, dropped connections and interrupts are
            # ambiguous, so their spend stays at the worst-case estimate.
            billed = 0.0 if isinstance(exc, anthropic.APIStatusError) else None
            inv = ModelInvocation(**base, model_id=route.model, success=False,
                                  latency_ms=_ms(started), actual_cost_usd=billed,
                                  request_id=getattr(exc, "request_id", None),
                                  failure_reason=_describe(exc))
            self._finish(inv)
            if isinstance(exc, anthropic.APIError):
                raise GatewayError(f"{operation} failed: {inv.failure_reason}", inv) from exc
            raise

        inv = self._invocation_from(message, base, started, request_id)
        self._finish(inv)
        if message.stop_reason == "refusal":
            raise ModelRefusal(f"{operation} was declined: {inv.failure_reason}", inv)
        text = "".join(b.text for b in message.content if getattr(b, "type", None) == "text")
        return GatewayResponse(text=text, stop_reason=message.stop_reason,
                               truncated=message.stop_reason == "max_tokens",
                               invocation=inv, message=message)

    # -- budget ------------------------------------------------------------

    def _count_input(self, shared: dict[str, Any]) -> int:
        try:
            return self.client.beta.messages.count_tokens(**shared).input_tokens
        except anthropic.APIError:
            # Counting failed: estimate high (2 characters per token) rather than skip the check.
            text = json.dumps([shared["system"], shared["messages"]], default=str)
            return math.ceil(len(text) / 2)

    def _check_budget(self, *, task_id: str | None, operation: str, model: str,
                      worst: float) -> None:
        task_limit, day_limit = self.limits.task_budget_usd, self.limits.daily_budget_usd
        spent_task = self.store.spend_for_task(task_id) if task_id else 0.0
        spent_today = self.store.spend_since(start_of_local_day(self.now()))
        breaches = []
        # Without a task the call is its own task, so the per-task limit caps the call.
        if spent_task + worst > task_limit:
            breaches.append(f"task budget ${task_limit:.2f}")
        if spent_today + worst > day_limit:
            breaches.append(f"daily budget ${day_limit:.2f}")
        if not breaches:
            return
        approval = ApprovalRecord(
            task_id=task_id, level=1, kind="budget_hold",
            summary=(f"{operation} could cost up to ${worst:.4f}, which would pass the "
                     f"{' and '.join(breaches)}."),
            details=dict(operation=operation, model=model, worst_case_usd=round(worst, 6),
                         spent_task_usd=round(spent_task, 6),
                         spent_today_usd=round(spent_today, 6),
                         task_budget_usd=task_limit, daily_budget_usd=day_limit))
        self.store.create_approval(approval)
        self.store.log_event(task_id, "budget_hold", approval_id=approval.approval_id,
                             operation=operation, model=model, worst_case_usd=round(worst, 6))
        raise BudgetHold(approval)

    # -- request and accounting -------------------------------------------

    def _send(self, kwargs: dict[str, Any]) -> tuple[Any, str | None]:
        # Streaming avoids HTTP timeouts on long outputs; we only need the final message.
        with self.client.beta.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()
            return message, getattr(stream, "request_id", None)

    def _invocation_from(self, message: Any, base: dict[str, Any], started: float,
                         request_id: str | None) -> ModelInvocation:
        usage = message.usage
        # usage.iterations has one entry per attempt (e.g. a refused attempt and its
        # fallback); top-level usage covers only the attempt that produced the message.
        attempts = list(getattr(usage, "iterations", None) or []) or [usage]
        totals = dict(input_tokens=0, output_tokens=0, cache_read_tokens=0,
                      cache_creation_tokens=0)
        cost: float | None = 0.0
        for a in attempts:
            # Plain calls report attempts without a model; then it's the served model.
            model = getattr(a, "model", None) or message.model
            tokens = dict(input_tokens=a.input_tokens or 0, output_tokens=a.output_tokens or 0,
                          cache_read_tokens=a.cache_read_input_tokens or 0,
                          cache_write_tokens=a.cache_creation_input_tokens or 0)
            totals["input_tokens"] += tokens["input_tokens"]
            totals["output_tokens"] += tokens["output_tokens"]
            totals["cache_read_tokens"] += tokens["cache_read_tokens"]
            totals["cache_creation_tokens"] += tokens["cache_write_tokens"]
            attempt_cost = self.pricing.cost(model, **tokens)
            cost = None if attempt_cost is None or cost is None else cost + attempt_cost
        if cost is None:
            # Unknown price: keep actual empty so spend falls back to the worst-case estimate.
            self.store.log_event(base["task_id"], "unpriced_model", model=message.model)

        refused = message.stop_reason == "refusal"
        failure = None
        if refused:
            details = getattr(message, "stop_details", None)
            failure = f"refusal:{getattr(details, 'category', None) or 'unspecified'}"
        return ModelInvocation(
            **base, **totals, model_id=message.model, actual_cost_usd=cost,
            latency_ms=_ms(started), success=not refused, failure_reason=failure,
            fallback_used=any(getattr(a, "type", None) == "fallback_message" for a in attempts),
            stop_reason=message.stop_reason, request_id=request_id)

    def _finish(self, inv: ModelInvocation) -> None:
        self.store.record_invocation(inv)
        self.store.log_event(inv.task_id, "model_call_finished",
                             invocation_id=inv.invocation_id, operation=inv.operation_id,
                             model=inv.model_id, success=inv.success,
                             stop_reason=inv.stop_reason, failure_reason=inv.failure_reason,
                             input_tokens=inv.input_tokens, output_tokens=inv.output_tokens,
                             cache_read_tokens=inv.cache_read_tokens,
                             cost_usd=inv.actual_cost_usd, latency_ms=inv.latency_ms)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _describe(exc: BaseException) -> str:
    """Error class, status and message only; never the request or headers."""
    status = getattr(exc, "status_code", None)
    msg = getattr(exc, "message", None) or str(exc)
    return f"{type(exc).__name__}" + (f" ({status})" if status else "") + f": {msg[:200]}"
