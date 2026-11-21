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
    for i, rev in enumerate(view.reviews, 1):
        print(f"Review {i}: {rev.verdict} (rule {rev.matched_rule}, {rev.tier})"
              + (f" - {rev.summary[:150]}" if rev.summary else ""))
    print("Events: " + ", ".join(e["kind"] for e in view.events))
    return EXIT_OK


_STEP_LABELS = {"setup": "worktree ready", "plan": "plan ready (Opus)",
                "builder": "Builder finished", "tester": "Tester finished",
                "checks": "tests and lint ran", "adjudicate": "Code Joe judged the failure",
                "package": "work committed on its branch",
                "review": "Guardian reviewed it", "revise": "Guardian sent it back (REVISE)",
                "deliver": "PASS: ready for you", "escalate": "ESCALATE: needs you",
                "finish": "stopped"}


def _step(node: str) -> None:
    print(f"  · {_STEP_LABELS.get(node, node)}", file=sys.stderr, flush=True)


def _print_outcome(out: core.RunOutcome) -> int:
    if out.outcome == "held":
        for h in out.holds:
            print(f"HOLD ({h['node']}): {h['summary']}")
            print(f"  Approve: ezra approve {h['approval_id']}    "
                  f"Reject: ezra reject {h['approval_id']}")
        print(f"Spent so far: ${out.spend_usd:.4f}. The task is paused and saved.")
        return EXIT_HOLD
    if out.outcome == "stopped":
        print(f"Code Joe stopped: {'; '.join(out.stopped) or 'unknown reason'}")
        print(f"Spent: ${out.spend_usd:.4f}")
        return EXIT_ERROR
    r, rev = out.result, out.review
    pytest_run = next((c for c in r.command_runs if c.command == "pytest"), None)
    passed = sum(c.outcome == "passed" for c in pytest_run.cases) if pytest_run else 0
    total = len(pytest_run.cases) if pytest_run else 0
    revised = " after one REVISE" if out.reviews > 1 else ""
    print(f"Guardian verdict: {rev.verdict}{revised} (rule {rev.matched_rule}, {rev.tier}).")
    print(f"Branch {r.branch}: {len(r.changed_files)} files. Tests {passed}/{total} passed. "
          f"Cost ${out.spend_usd:.4f}.")
    for c in rev.criteria_results:
        print(f"  {c.criterion_id}: {c.status}" + (f"  ({c.evidence[:90]})" if c.evidence
                                                   else ""))
    for f in rev.findings:
        print(f"  finding [{f.severity}] {f.code}: {f.message[:120]}")
    if rev.summary:
        print(f"Guardian: {rev.summary[:300]}")
    if out.outcome == "passed":
        print(f"Nothing was merged. Merging {r.branch} is your call.")
        return EXIT_OK
    print("Escalated to you: Ezra won't try again on its own.")
    return EXIT_ERROR


def _run_guarded(fn) -> int:
    store = core.open_store()
    try:
        return _print_outcome(fn(store, core.open_gateway(store)))
    except core.RunError as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    except MissingCredentials as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    finally:
        store.close()


def _cmd_run(args: argparse.Namespace) -> int:
    print(f"Code Joe is working on {args.task_id}…", file=sys.stderr)
    return _run_guarded(lambda store, gw: core.run_task(
        store, gw, args.task_id, task_budget_usd=args.task_budget, on_step=_step))


def _cmd_approve(args: argparse.Namespace) -> int:
    return _run_guarded(lambda store, gw: core.answer_hold(
        store, gw, args.approval_id, True, extend_usd=args.extend, on_step=_step))


def _cmd_reject(args: argparse.Namespace) -> int:
    return _run_guarded(lambda store, gw: core.answer_hold(
        store, gw, args.approval_id, False, on_step=_step))


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


def _print_score(s) -> None:
    print(f"{s.kind} (benchmarks v{s.benchmark_version}): "
          + ("PASS" if s.passed else "FAIL") + ("" if s.clean or not s.passed else
                                                 " with warnings"))
    for g in s.gates:
        print(f"  gate     {g}")
    for w in s.warnings:
        print(f"  warning  {w}")
    if s.metrics:
        print("  " + " · ".join(f"{k} {v}" for k, v in s.metrics.items()))


def _cmd_bench(args: argparse.Namespace) -> int:
    if args.kind == "references":
        results = core.check_references()
        for ex, s, ok in results:
            want = "best: passes cleanly" if ex.expected_to_pass else "weak: gets caught"
            print(f"{'ok  ' if ok else 'FAIL'}  {ex.id:34} {want} "
                  f"({len(s.gates)} gates, {len(s.warnings)} warnings)")
        return EXIT_OK if all(ok for *_, ok in results) else EXIT_ERROR
    if not args.path:
        print("give a file to score, or - for stdin", file=sys.stderr)
        return EXIT_ERROR
    try:
        text = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
    except OSError as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    s = core.benchmark(args.kind, text)
    _print_score(s)
    return EXIT_OK if s.passed else EXIT_ERROR


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
    p_run = sub.add_parser("run", help="Have Code Joe work on a created task")
    p_run.add_argument("task_id")
    p_run.add_argument("--task-budget", type=float, default=None,
                       help="Lower the task's budget cap for this run (USD)")
    p_run.set_defaults(func=_cmd_run)
    p_ok = sub.add_parser("approve", help="Approve a HOLD and resume the task")
    p_ok.add_argument("approval_id")
    p_ok.add_argument("--extend", type=float, default=None,
                      help="How much to raise the cap (USD). Default: just enough")
    p_ok.set_defaults(func=_cmd_approve)
    p_no = sub.add_parser("reject", help="Reject a HOLD and stop the task")
    p_no.add_argument("approval_id")
    p_no.set_defaults(func=_cmd_reject)
    p_b = sub.add_parser("bench", help="Score an output against the reference benchmarks")
    p_b.add_argument("kind", choices=["criteria", "standard", "answer", "review", "eval",
                                      "references"],
                     help="what the file is; 'references' self-checks docs/reference-outputs")
    p_b.add_argument("path", nargs="?", help="file to score, or - for stdin")
    p_b.set_defaults(func=_cmd_bench)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
