"""Command-line interface. A thin client over ezra.core: it parses arguments and prints."""

from __future__ import annotations

import argparse
import sys

import anthropic

from ezra import core
from ezra.contracts import ModelInvocation
from ezra.gateway import BudgetHold, GatewayError, MissingCredentials, ModelRefusal

EXIT_OK, EXIT_ERROR, EXIT_HOLD = 0, 1, 2


def _footer(inv: ModelInvocation) -> str:
    cost = f"${inv.actual_cost_usd:.6f}" if inv.actual_cost_usd is not None else "cost unknown"
    model = inv.model_id + (f" (fallback from {inv.requested_model})" if inv.fallback_used else "")
    return (f"{model} · in {inv.input_tokens} · out {inv.output_tokens} · "
            f"cache read {inv.cache_read_tokens} / write {inv.cache_creation_tokens} · "
            f"{cost} · {inv.latency_ms / 1000:.1f}s")


def _cmd_ask(args: argparse.Namespace) -> int:
    store = core.open_store()
    try:
        result = core.ask(core.open_gateway(store), " ".join(args.question))
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
    except anthropic.AnthropicError as e:  # e.g. no credentials found
        print(f"Couldn't reach Claude: {e}. Is ANTHROPIC_API_KEY set?", file=sys.stderr)
        return EXIT_ERROR
    finally:
        store.close()
    print(result.text)
    if result.truncated:
        print("[answer cut off at the length limit]", file=sys.stderr)
    print(_footer(result.invocation), file=sys.stderr)
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
    p_ask = sub.add_parser("ask", help="Ask Ezra a question")
    p_ask.add_argument("question", nargs="+")
    p_ask.set_defaults(func=_cmd_ask)
    p_apr = sub.add_parser("approvals", help="List decisions waiting for you")
    p_apr.set_defaults(func=_cmd_approvals)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
