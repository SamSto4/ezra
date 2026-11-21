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
        print(f"Run it with: ezra run {env.task_id}    See it: ezra task {env.task_id}")
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
    _print_learning(out.learning)
    if out.outcome == "passed":
        print(f"Nothing was merged. Merging {r.branch} is your call.")
        return EXIT_OK
    print("Escalated to you: Ezra won't try again on its own.")
    return EXIT_ERROR


def _print_learning(learn) -> None:
    if learn is None:
        return
    parts = []
    if learn.added:
        parts.append(f"{len(learn.added)} new lesson(s) ({', '.join(learn.added)})")
    if learn.merged:
        parts.append(f"{len(learn.merged)} reinforced")
    if learn.retired:
        parts.append(f"{len(learn.retired)} retired")
    if learn.rejected:
        parts.append(f"{len(learn.rejected)} rejected by the checks")
    if learn.rated:
        parts.append(f"{len(learn.rated)} rated")
    summary = "; ".join(parts) or "nothing new"
    cost = f" (${learn.cost_usd:.4f})" if learn.reflected else ""
    print(f"Learned: {summary}{cost}." + (f" {learn.skipped}." if learn.skipped else ""))
    if learn.added:
        print("  New lessons are live now. See them with: ezra lessons; undo one with: "
              "ezra lessons retire <id>")


def _run_guarded(fn, task_id: str | None = None) -> int:
    store = core.open_store()
    try:
        return _print_outcome(fn(store, core.open_gateway(store)))
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing is lost: finished steps are saved."
              + (f" Continue with: ezra run {task_id} --resume" if task_id else ""),
              file=sys.stderr)
        return EXIT_ERROR
    except core.RunError as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    except MissingCredentials as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    finally:
        store.close()


def _cmd_run(args: argparse.Namespace) -> int:
    if args.resume:
        if args.task_budget is not None:
            print("--task-budget can't be changed on --resume.", file=sys.stderr)
            return EXIT_ERROR
        print(f"Resuming {args.task_id} from its last saved step…", file=sys.stderr)
        return _run_guarded(lambda store, gw: core.resume_task(
            store, gw, args.task_id, on_step=_step), args.task_id)
    print(f"Code Joe is working on {args.task_id}…", file=sys.stderr)
    return _run_guarded(lambda store, gw: core.run_task(
        store, gw, args.task_id, task_budget_usd=args.task_budget, on_step=_step,
        memory=args.memory), args.task_id)


def _cmd_review(args: argparse.Namespace) -> int:
    print(f"Guardian is reviewing {args.task_id}…", file=sys.stderr)
    return _run_guarded(lambda store, gw: core.review_task(
        store, gw, args.task_id, on_step=_step), args.task_id)


def _cmd_abandon(args: argparse.Namespace) -> int:
    store = core.open_store()
    try:
        before = core.abandon_task(store, args.task_id, args.reason or "")
    except core.RunError as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    finally:
        store.close()
    print(f"Task {args.task_id} was {before}; it's now failed. Its branch "
          f"ezra/{args.task_id} and worktree were kept.")
    return EXIT_OK


def _cmd_approve(args: argparse.Namespace) -> int:
    return _run_guarded(lambda store, gw: core.answer_hold(
        store, gw, args.approval_id, True, extend_usd=args.extend, on_step=_step))


def _cmd_reject(args: argparse.Namespace) -> int:
    return _run_guarded(lambda store, gw: core.answer_hold(
        store, gw, args.approval_id, False, on_step=_step))


def _cmd_trace(args: argparse.Namespace) -> int:
    store = core.open_store()
    try:
        tr = core.get_trace(store, args.task_id)
        if tr is not None and args.text:
            text = store.get_text(args.text)
    finally:
        store.close()
    if tr is None:
        print(f"No task '{args.task_id}'.", file=sys.stderr)
        return EXIT_ERROR
    if args.text:
        if text is None:
            print(f"No stored text '{args.text}'.", file=sys.stderr)
            return EXIT_ERROR
        print(text)
        return EXIT_OK
    env = tr.envelope
    print(f"Trace {env.task_id}  [{tr.status}]  {env.description[:100]}")
    print(f"{'time':8}  {'step':10}  what happened")
    t0 = tr.rows[0].at if tr.rows else None
    for row in tr.rows:
        rel = f"+{(row.at - t0).total_seconds():6.1f}s" if t0 else ""
        print(f"{rel:8}  {row.step:10}  {row.detail}")
        if args.verbose and row.invocation is not None:
            inv = row.invocation
            print(f"{'':20}prompt {inv.prompt_version or '(not recorded)'}")
            for c in inv.context:
                print(f"{'':20}  context {c.label}: {c.chars} chars  (--text {c.sha[:12]})")
            if inv.response_hash:
                print(f"{'':20}  reply: ezra trace {env.task_id} --text "
                      f"{inv.response_hash[:12]}")
    print()
    print(f"{'operation':20} {'calls':>5} {'in':>8} {'out':>7} {'cache r':>8} "
          f"{'cache w':>8} {'cost':>9} {'time':>7}")
    for t in tr.totals:
        print(f"{t.operation:20} {t.calls:5} {t.input_tokens:8} {t.output_tokens:7} "
              f"{t.cache_read_tokens:8} {t.cache_creation_tokens:8} ${t.cost_usd:8.4f} "
              f"{t.latency_ms / 1000:6.1f}s")
    tot = lambda f: sum(getattr(t, f) for t in tr.totals)  # noqa: E731
    print(f"{'total':20} {tr.calls:5} {tot('input_tokens'):8} {tot('output_tokens'):7} "
          f"{tot('cache_read_tokens'):8} {tot('cache_creation_tokens'):8} "
          f"${tot('cost_usd'):8.4f} {tot('latency_ms') / 1000:6.1f}s")
    if tr.unpriced_calls:
        print(f"({tr.unpriced_calls} call(s) had no known price and are counted at their "
              "worst case.)")
    for i, rev in enumerate(tr.reviews, 1):
        print(f"Review {i}: {rev.verdict} (rule {rev.matched_rule}, {rev.tier})")
    for a in tr.approvals:
        print(f"Approval {a.approval_id}: {a.kind}, {a.status}")
    verdict = tr.verdict or "no Guardian verdict yet"
    print(f"Outcome: {tr.status}, {verdict}. Cost for this task: ${tr.spend_usd:.4f} "
          f"over {tr.calls} model calls.")
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


def _cmd_learn(args: argparse.Namespace) -> int:
    store = core.open_store()
    try:
        learn = core.learn(store, core.open_gateway(store), args.task_id)
    except MissingCredentials as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    finally:
        store.close()
    if learn.skipped and not (learn.reflected or learn.rated):
        print(f"Nothing learned: {learn.skipped}.")
        return EXIT_OK
    _print_learning(learn)
    return EXIT_OK


def _lesson_line(lsn) -> str:
    scope = lsn.project or "any project"
    return (f"{lsn.lesson_id}  [{lsn.status} · {lsn.source} · {lsn.kind}]  {lsn.operation} · "
            f"{scope} · +{lsn.helpful}/-{lsn.harmful} · used {lsn.uses} · "
            f"seen in {len(lsn.evidence)} task(s) · v{lsn.version}\n"
            f"    When {lsn.trigger.rstrip('.')}: {lsn.text}")


def _cmd_lessons(args: argparse.Namespace) -> int:
    store = core.open_store()
    try:
        if args.action == "show":
            found = core.lesson_history(store, args.lesson_id)
            if found is None:
                print(f"No lesson '{args.lesson_id}'.", file=sys.stderr)
                return EXIT_ERROR
            lesson, history = found
            print(_lesson_line(lesson))
            print("Evidence: " + ", ".join(lesson.evidence))
            for h in history:
                print(f"  v{h['version']}  {h['created_at'][:19]}Z  {h['action']}"
                      + (f"  ({h['task_id']})" if h["task_id"] else "")
                      + (f"  {h['reason'][:120]}" if h["reason"] else ""))
            return EXIT_OK
        if args.action == "retire":
            try:
                lesson = core.retire_lesson(store, args.lesson_id)
            except core.RunError as e:
                print(str(e), file=sys.stderr)
                return EXIT_ERROR
            print(f"Retired {lesson.lesson_id}. It stays in the history but won't be used.")
            return EXIT_OK
        lessons = core.list_lessons(store, include_retired=args.all)
    finally:
        store.close()
    if not lessons:
        print("No lessons yet. Run a task with --memory lessons to start learning.")
    for lsn in lessons:
        print(_lesson_line(lsn))
    return EXIT_OK


def _cmd_experiment(args: argparse.Namespace) -> int:
    import tempfile
    from pathlib import Path

    from ezra import experiment as ex
    tasks = ex.load_tasks()
    if args.action == "validate":
        bad = 0
        with tempfile.TemporaryDirectory() as tmp:
            for t in tasks:
                check = ex.validate_task(t, Path(tmp))
                bad += not check.ok
                print(f"{'ok  ' if check.ok else 'FAIL'} {t.id} [{t.split} · {t.category}]"
                      + ("" if check.ok else f": {'; '.join(check.problems)}"))
        print(f"{len(tasks) - bad}/{len(tasks)} tasks are fair.")
        return EXIT_OK if not bad else EXIT_ERROR
    if args.action == "report":
        rows = ex.load_rows()
        if not rows:
            print("No results yet.")
            return EXIT_OK
        for arm, s in ex.summarize(rows).items():
            cps = (f"${s['cost_per_success_usd']:.4f}" if s["cost_per_success_usd"] is not None
                   else "n/a")
            print(f"{arm:15} held-out n={s['n']} runs={s['runs']}  hidden success "
                  f"{s['success_rate']:.0%}  Guardian PASS {s['guardian_pass_rate']:.0%}  "
                  f"mean cost ${s['mean_cost_usd']:.4f}  cost/success {cps}")
        for arm in ("lessons", "budget_matched"):
            d = ex.paired_difference(rows, arm)
            if d:
                print(f"{arm} - control: {d['diff']:+.1%} (95% CI {d['ci_low']:+.1%} to "
                      f"{d['ci_high']:+.1%}, {d['pairs']} paired tasks)")
        return EXIT_OK
    arms = args.arms.split(",") if getattr(args, "arms", None) else list(ex.ARMS)
    unknown = [a for a in arms if a not in ex.ARMS]
    if unknown:
        print(f"Unknown arm(s): {', '.join(unknown)}. Arms: {', '.join(ex.ARMS)}",
              file=sys.stderr)
        return EXIT_ERROR
    est = ex.estimate(tasks, arms, args.runs)
    print(f"{len(tasks)} tasks x {len(arms)} arm(s) x {args.runs} run(s) = {est.task_runs} "
          f"task runs + {est.reflections} reflections: about ${est.low_usd:.2f}-"
          f"${est.high_usd:.2f}.")
    if args.action == "estimate":
        return EXIT_OK
    if not args.confirm:
        print("Nothing was run. Live runs spend money: add --max-usd and --confirm once "
              "you've agreed to the cost.")
        return EXIT_HOLD
    try:
        for run in range(1, args.runs + 1):
            for arm in arms:
                print(f"Running {arm}, run {run}…", file=sys.stderr)
                ex.run_arm(arm, run, tasks, max_usd=args.max_usd, on_task=lambda r: print(
                    f"  {r.task}: {r.outcome}, hidden {'pass' if r.hidden_pass else 'FAIL'}, "
                    f"${r.cost_usd:.4f}", file=sys.stderr))
    except (core.RunError, MissingCredentials) as e:
        print(str(e), file=sys.stderr)
        return EXIT_ERROR
    print("Done. See the results with: ezra experiment report")
    return EXIT_OK


def _cmd_ui(args: argparse.Namespace) -> int:
    from ezra.api import UI_DIST, serve
    if not UI_DIST.is_dir():
        print("The UI isn't built yet: run `npm install && npm run build` in ui/. "
              "The API still runs.", file=sys.stderr)
    print(f"Ezra UI on http://127.0.0.1:{args.port} (this Mac only). Ctrl-C to stop.",
          file=sys.stderr)
    serve(args.port)
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
    p_tr = sub.add_parser("trace", help="Show every step, model call and cost of a task")
    p_tr.add_argument("task_id")
    p_tr.add_argument("-v", "--verbose", action="store_true",
                      help="Also show prompt versions and injected context per call")
    p_tr.add_argument("--text", metavar="SHA", default=None,
                      help="Print one stored prompt, context or reply by its hash")
    p_tr.set_defaults(func=_cmd_trace)
    p_ui = sub.add_parser("ui", help="Open Ezra's local web UI")
    p_ui.add_argument("--port", type=int, default=8765)
    p_ui.set_defaults(func=_cmd_ui)
    p_apr = sub.add_parser("approvals", help="List decisions waiting for you")
    p_apr.set_defaults(func=_cmd_approvals)
    p_run = sub.add_parser("run", help="Have Code Joe work on a created task")
    p_run.add_argument("task_id")
    p_run.add_argument("--task-budget", type=float, default=None,
                       help="Lower the task's budget cap for this run (USD)")
    p_run.add_argument("--resume", action="store_true",
                       help="Continue a task that was cut off (crash or Ctrl-C)")
    p_run.add_argument("--memory", choices=["off", "lessons", "frozen"], default=None,
                       help="lessons: use and learn; frozen: use without learning "
                            "(default: config/learning.yaml)")
    p_run.set_defaults(func=_cmd_run)
    p_rv = sub.add_parser("review", help="Give Guardian review to a task that never got one")
    p_rv.add_argument("task_id")
    p_rv.set_defaults(func=_cmd_review)
    p_ab = sub.add_parser("abandon", help="Close a stuck task as failed (keeps its branch)")
    p_ab.add_argument("task_id")
    p_ab.add_argument("--reason", default=None)
    p_ab.set_defaults(func=_cmd_abandon)
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
    p_learn = sub.add_parser("learn", help="Learn lessons from a finished task")
    p_learn.add_argument("task_id")
    p_learn.set_defaults(func=_cmd_learn)
    p_les = sub.add_parser("lessons", help="List, inspect or retire learned lessons")
    p_les.set_defaults(func=_cmd_lessons, action="list")
    les_sub = p_les.add_subparsers(dest="action")
    p_list = les_sub.add_parser("list", help="List lessons (default)")
    p_list.add_argument("--all", action="store_true", help="Include retired lessons")
    p_show = les_sub.add_parser("show", help="A lesson and its version history")
    p_show.add_argument("lesson_id")
    p_ret = les_sub.add_parser("retire", help="Stop using a lesson (kept in history)")
    p_ret.add_argument("lesson_id")
    p_les.add_argument("--all", action="store_true", help="Include retired lessons")
    p_ex = sub.add_parser("experiment", help="The progressive learning experiment")
    ex_sub = p_ex.add_subparsers(dest="action", required=True)
    ex_sub.add_parser("validate", help="Check every task is fair (no model calls)")
    ex_sub.add_parser("report", help="Summarize the results so far")
    for name, text in (("estimate", "Estimate the cost of a run (no model calls)"),
                       ("run", "Run arms live (spends money; needs --confirm)")):
        p = ex_sub.add_parser(name, help=text)
        p.add_argument("--arms", default=None, help="Comma-separated: control,lessons,"
                       "budget_matched (default: all)")
        p.add_argument("--runs", type=int, default=3, help="Runs per arm (default 3)")
        if name == "run":
            p.add_argument("--max-usd", type=float, required=True,
                           help="Hard cap on spend for this whole command")
            p.add_argument("--confirm", action="store_true",
                           help="You've seen the estimate and agree to spend up to --max-usd")
    p_ex.set_defaults(func=_cmd_experiment)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
