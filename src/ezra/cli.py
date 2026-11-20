"""Command-line interface. A thin client over ezra.core: it parses arguments and prints."""

from __future__ import annotations

import argparse
import sys

import anthropic

from ezra import core
from ezra.contracts import AcceptanceCriterion, ModelInvocation
from ezra.gateway import BudgetHold, GatewayError, MissingCredentials, ModelRefusal
from ezra.intake import IntakeError, Route

EXIT_OK, EXIT_ERROR, EXIT_HOLD = 0, 1, 2


def _footer(invocations: list[ModelInvocation]) -> str:
    inv = invocations[-1]
    costs = [i.actual_cost_usd for i in invocations]
    cost = (f"${sum(costs):.6f}" if all(c is not None for c in costs) else "cost unknown")
    model = inv.model_id + (f" (fallback from {inv.requested_model})" if inv.fallback_used else "")
    calls = f" · {len(invocations)} calls" if len(invocations) > 1 else ""
    return (f"{model}{calls} · in {sum(i.input_tokens for i in invocations)} · "
            f"out {sum(i.output_tokens for i in invocations)} · "
            f"cache read {sum(i.cache_read_tokens for i in invocations)} / "
            f"write {sum(i.cache_creation_tokens for i in invocations)} · {cost} · "
            f"{sum(i.latency_ms for i in invocations) / 1000:.1f}s")


def _criterion_line(c: AcceptanceCriterion) -> str:
    how = f"{c.verification}:{c.check}" if c.check else str(c.verification)
    return f"  {c.id} [{c.severity} · {how}] {c.text}"


def _cmd_ask(args: argparse.Namespace) -> int:
    store = core.open_store()
    try:
        result = core.ask(core.open_gateway(store), " ".join(args.request))
    except MissingCredentials as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    except BudgetHold as hold:
        print(f"HOLD: {hold.approval.summary}", file=sys.stderr)
        print(f"Nothing was sent to the model. Approval id: {hold.approval.approval_id}",
              file=sys.stderr)
        return EXIT_HOLD
    except ModelRefusal as e:
        print(f"Claude declined this request ({e.invocation.failure_reason}).", file=sys.stderr)
        return EXIT_ERROR
    except GatewayError as e:
        print(f"Model call failed: {e.invocation.failure_reason}", file=sys.stderr)
        return EXIT_ERROR
    except IntakeError as e:
        print(f"Intake failed: {e}", file=sys.stderr)
        return EXIT_ERROR
    except anthropic.AnthropicError as e:
        print(f"Couldn't reach Claude: {e}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        store.close()

    if result.route is Route.DIRECT:
        print(result.answer)
    elif result.route is Route.UNSUPPORTED:
        print(f"Ezra can't do this yet: {result.unsupported_reason}")
    else:
        env = result.envelope
        print(f"Created task {env.task_id} for Code Joe: {result.task_title}")
        print(f"Goal: {env.description}")
        print("Acceptance criteria:")
        for c in env.acceptance_criteria:
            print(_criterion_line(c))
        for rule in env.constraints:
            print(f"  constraint: {rule}")
        print("Code Joe starts working on tasks in M4. "
              f"See it again with: ezra task {env.task_id}")
    print(f"[{result.route}] " + _footer(result.invocations), file=sys.stderr)
    return EXIT_OK


def _cmd_task(args: argparse.Namespace) -> int:
    store = core.open_store()
    try:
        view = core.get_task(store, args.task_id)
    finally:
        store.close()
    if view is None:
        print(f"No task '{args.task_id}'.", file=sys.stderr)
        return EXIT_ERROR
    env = view.envelope
    print(f"{env.task_id}  [{view.status}]  for {env.target_department}")
    print(f"Goal: {env.description}")
    print(f"Project: {env.project_ref}")
    print("Acceptance criteria:")
    for c in env.acceptance_criteria:
        print(_criterion_line(c))
    for rule in env.constraints:
        print(f"  constraint: {rule}")
    print(f"Spend so far: ${view.spend_usd:.6f} of ${env.budget.task_limit_usd:.2f}")
    print("Events: " + ", ".join(e["kind"] for e in view.events))
    return EXIT_OK


def _cmd_approvals(_: argparse.Namespace) -> int:
    store = core.open_store()
    try:
        pending = core.pending_approvals(store)
    finally:
        store.close()
    if not pending:
        print("No pending approvals.")
    for a in pending:
        print(f"{a.approval_id}  level {a.level}  {a.kind}  {a.created_at:%Y-%m-%d %H:%M}Z")
        print(f"    {a.summary}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ezra", description="Ezra, your AI agent.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_ask = sub.add_parser("ask", help="Ask Ezra a question or give it a coding task")
    p_ask.add_argument("request", nargs="+")
    p_ask.set_defaults(func=_cmd_ask)
    p_task = sub.add_parser("task", help="Show a saved task")
    p_task.add_argument("task_id")
    p_task.set_defaults(func=_cmd_task)
    p_apr = sub.add_parser("approvals", help="List decisions waiting for you")
    p_apr.set_defaults(func=_cmd_approvals)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
