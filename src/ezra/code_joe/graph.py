"""Code Joe as a LangGraph graph.

    setup → plan → (builder ∥ tester) → checks ─pass──────────────→ package → review
                          ▲                │                                    │
                          │                ├─fail, iterations left─→ adjudicate ─┤ (back to
                          │                └─fail, cap reached────→ package     │  builder/
                          │                                                      │  tester)
                          └──── revise ◄── REVISE (once per task, tests frozen) ─┤
                                           PASS → deliver → END                  │
                                           ESCALATE → escalate → END ◄───────────┘
    any step that stops (error or a rejected HOLD) → finish → END

Guardian (M5): review runs Tier 1 (free) and, unless Tier 1 already decided, Tier 2 (one
Opus call). The D-002 table picks the verdict. REVISE consumes the task's one correction
cycle (D-004): Builder gets Guardian's corrections, Tester doesn't run again, and failures
after that go straight back to Builder. The second review can't REVISE, so there is never a
third attempt.

Pausing for a budget HOLD (D-009 Level 1):
- A model call that would pass the budget raises BudgetHold inside a step. The step saves a
  pending approval with a stable id and calls LangGraph's interrupt(); the run pauses and the
  checkpointer (SQLite) saves the graph's state.
- `ezra approve` / `ezra reject` resolve the stored approval first, then resume, even from a
  new process. LangGraph reruns the paused step from its first line. The step reads the
  decision from the stored record when it starts, because on a rerun the hold may not
  happen again (a parallel reservation may be gone). A rejection stops the step before any
  model call, and an extension raises only the cap the hold named (task or daily). Work done
  before the pause in that step is redone (files written stay on disk). That's the Phase 1
  trade-off.
- Only our own exception types are caught in steps. interrupt() works by raising, so a
  catch-all would swallow the pause.
- Counters change only through a step's returned state, so a rerun can't count twice.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ezra.code_joe.agents import Plan, adjudicate, build, make_plan, write_tests
from ezra.code_joe.sandbox import run_pytest, run_ruff
from ezra.code_joe.tools import AgentError
from ezra.code_joe.workspace import Worktree, changed_files, commit_all, create_worktree
from ezra.contracts import (
    ApprovalStatus,
    CommandRun,
    CriterionStatus,
    Department,
    DeterministicCheck,
    LoopCounters,
    ResultStatus,
    ReviewTier,
    StandardDepartmentResult,
    TaskEnvelope,
    TaskStatus,
    TokenMetrics,
    Verdict,
    Verification,
)
from ezra.gateway import BudgetHold, Gateway, GatewayError, ModelRefusal
from ezra.guardian.tier1 import criterion_pattern, is_acceptance_case, run_tier1
from ezra.guardian.tier2 import run_tier2
from ezra.guardian.verdict import VerdictInput, build_review
from ezra.learner.retrieval import LessonProvider
from ezra.store import Store


class CodeJoeState(TypedDict, total=False):
    task_id: str
    task_cap: float
    daily_cap: float
    budget_extra_task: Annotated[float, operator.add]  # raised by approved HOLDs
    budget_extra_day: Annotated[float, operator.add]
    worktree: str
    branch: str
    base_commit: str
    plan: dict
    counters: dict
    run_builder: bool
    run_tester: bool
    builder_feedback: str
    tester_feedback: str
    checks: list[dict]
    missing: list[str]
    passed: bool
    stopped: Annotated[list[str], operator.add]
    outcome: str
    result: dict
    review: dict
    memory: str  # "off", "lessons" or "frozen" (config/learning.yaml), fixed for the run


@dataclass
class Context:
    store: Store
    gateway: Gateway
    worktrees_dir: Path
    test_timeout: int
    lessons: LessonProvider | None = None  # progressive learning (D-012)


class Stopped(Exception):
    """The user rejected a HOLD."""


class _Gate:
    """Wraps Gateway.call for one step execution: applies the run's caps and turns a
    BudgetHold into a LangGraph pause.

    The decision on a HOLD is read from the stored approval record when the step (re)starts,
    not only from the replayed pause: on a rerun the hold may not happen again (a parallel
    reservation may be gone), and a rejection or extension must still apply."""

    def __init__(self, ctx: Context, state: CodeJoeState, node: str):
        self.ctx, self.state, self.node = ctx, state, node
        c = state.get("counters", {})
        tag = f"c{c.get('correction_cycles_used', 0)}i{c.get('internal_iterations_used', 0)}"
        self.prefix = f"apr_{state['task_id']}_{node}_{tag}_"
        self.extra_task = state.get("budget_extra_task", 0.0)
        self.extra_day = state.get("budget_extra_day", 0.0)
        self.added_task = self.added_day = 0.0
        self.applied: set[str] = set()
        self.rejected: str | None = None
        self.k = 0
        for rec in ctx.store.approvals_for_task(state["task_id"]):
            if rec.approval_id.startswith(self.prefix):
                self._apply(rec)

    def _apply(self, rec: Any) -> None:
        if rec.approval_id in self.applied or rec.status is ApprovalStatus.PENDING:
            return
        self.applied.add(rec.approval_id)
        if rec.status is ApprovalStatus.REJECTED:
            self.rejected = f"budget HOLD {rec.approval_id} was rejected"
            return
        extend = float(rec.details.get("extend_usd", 0.0))
        breaches = rec.details.get("breaches", ["task"])
        if "task" in breaches:  # raise only the cap the approval named
            self.extra_task += extend
            self.added_task += extend
        if "daily" in breaches:
            self.extra_day += extend
            self.added_day += extend

    def update(self) -> dict:
        return {"budget_extra_task": self.added_task, "budget_extra_day": self.added_day}

    def call(self, **kwargs: Any) -> Any:
        if self.ctx.lessons is not None and self.state.get("memory") in ("lessons", "frozen"):
            # Lessons ride as a second cached system block. They're counted in the input,
            # so the budget check, fit and HOLD below cover them like any other token.
            context, refs = self.ctx.lessons.for_call(self.state["task_id"],
                                                      kwargs["operation"])
            if context:
                kwargs = {**kwargs, "system_context": context, "context_refs": refs}
        while True:
            if self.rejected:
                raise Stopped(self.rejected)
            try:
                return self.ctx.gateway.call(
                    **kwargs, task_budget_usd=self.state["task_cap"] + self.extra_task,
                    daily_budget_usd=self.state["daily_cap"] + self.extra_day,
                    approval_id=f"{self.prefix}{self.k}", persist_hold=False)
            except BudgetHold as hold:
                self._pause(hold)

    def _pause(self, hold: BudgetHold) -> None:
        store, task_id = self.ctx.store, self.state["task_id"]
        aid = hold.approval.approval_id
        store.create_approval(hold.approval)  # idempotent: same id on a rerun
        if aid not in self.applied:
            store.set_task_status(task_id, TaskStatus.HELD)
        interrupt({"approval_id": aid, "node": self.node, "summary": hold.approval.summary})
        # Resumed: the decision is in the stored record (answer_hold resolved it first).
        self.k += 1
        store.set_task_status(task_id, TaskStatus.RUNNING)
        rec = store.get_approval(aid)
        if rec is not None:
            self._apply(rec)


_STOPPING = (AgentError, GatewayError, ModelRefusal, Stopped)


def _envelope(ctx: Context, task_id: str) -> TaskEnvelope:
    found = ctx.store.get_task(task_id)
    if found is None:
        raise KeyError(f"No task '{task_id}'")
    return found[0]


def _failure_report(pytest_run: CommandRun, ruff_run: CommandRun, failed: list,
                    missing: list[str]) -> str:
    report = "\n".join(f"- {c.outcome}: {c.name}\n{c.message[-1200:]}" for c in failed)
    if pytest_run.exit_code not in (0, 1):
        report += f"\n\npytest exit code {pytest_run.exit_code}:\n" \
                  f"{pytest_run.output_excerpt[-2000:]}"
    if missing:
        report += f"\n\nCriteria with no acceptance test: {', '.join(missing)}"
    if ruff_run.exit_code not in (0, None):
        report += f"\n\nruff:\n{ruff_run.output_excerpt[-1500:]}"
    return report


def _tier1_corrections(env: TaskEnvelope, t1: Any, result: StandardDepartmentResult
                       ) -> list[str]:
    """Repair instructions when Tier 1 decides alone: name what's unmet and why."""
    by_id = {c.id: c for c in env.acceptance_criteria}
    out = [f"{r.criterion_id} is not met ({r.status}): {by_id[r.criterion_id].text}"
           + (f" Evidence: {r.evidence}" if r.evidence else "")
           for r in t1.criteria_results
           if r.status is not CriterionStatus.MET and r.criterion_id in t1.blocking_ids]
    out += [f"{f.code}: {f.message}" for f in t1.findings]
    pytest_run = next((c for c in result.command_runs if c.command == "pytest"), None)
    if pytest_run:
        out += [f"Failing test {c.name}: {c.message[-400:]}" for c in pytest_run.cases
                if c.outcome in ("failed", "error")][:5]
    return out


def build_graph(ctx: Context, checkpointer: Any = None):
    store = ctx.store

    def setup(state: CodeJoeState) -> dict:
        env = _envelope(ctx, state["task_id"])
        wt = create_worktree(env.project_ref, env.task_id, ctx.worktrees_dir)
        store.set_task_status(env.task_id, TaskStatus.RUNNING)
        store.log_event(env.task_id, "code_joe_started", branch=wt.branch,
                        worktree=str(wt.path), task_cap=state["task_cap"])
        return {"worktree": str(wt.path), "branch": wt.branch, "base_commit": wt.base_commit,
                "counters": env.counters.model_dump(), "run_builder": True,
                "run_tester": True, "builder_feedback": "", "tester_feedback": ""}

    def plan_node(state: CodeJoeState) -> dict:
        gate = _Gate(ctx, state, "plan")
        env = _envelope(ctx, state["task_id"])
        try:
            plan, _ = make_plan(gate.call, env, Path(state["worktree"]))
        except _STOPPING as e:
            return {"stopped": [f"plan: {e}"], **gate.update()}
        store.log_event(env.task_id, "plan_ready", steps=len(plan.steps),
                        interface=[i.symbol for i in plan.interface], test_file=plan.test_file)
        return {"plan": plan.model_dump(), **gate.update()}

    def builder_node(state: CodeJoeState) -> dict:
        gate = _Gate(ctx, state, "builder")
        env = _envelope(ctx, state["task_id"])
        try:
            run = build(gate.call, env, Plan(**state["plan"]), Path(state["worktree"]),
                        feedback=state.get("builder_feedback", ""))
        except _STOPPING as e:
            return {"stopped": [f"builder: {e}"], **gate.update()}
        store.log_event(env.task_id, "builder_done", turns=run.turns,
                        files=run.files_written, summary=run.summary[:500])
        return {**gate.update()}

    def tester_node(state: CodeJoeState) -> dict:
        gate = _Gate(ctx, state, "tester")
        env = _envelope(ctx, state["task_id"])
        try:
            run = write_tests(gate.call, env, Plan(**state["plan"]), Path(state["worktree"]),
                              feedback=state.get("tester_feedback", ""))
        except _STOPPING as e:
            return {"stopped": [f"tester: {e}"], **gate.update()}
        store.log_event(env.task_id, "tester_done", turns=run.turns,
                        files=run.files_written, summary=run.summary[:500])
        return {**gate.update()}

    def checks_node(state: CodeJoeState) -> dict:
        if state.get("stopped"):
            return {}
        env = _envelope(ctx, state["task_id"])
        wt = Path(state["worktree"])
        pytest_run = run_pytest(wt, ctx.test_timeout)
        ruff_run = run_ruff(wt, ctx.test_timeout)
        acceptance = [c for c in pytest_run.cases if is_acceptance_case(c.name)]
        missing = [c.id for c in env.acceptance_criteria
                   if c.verification is Verification.TEST
                   and not any(criterion_pattern(c.id).search(a.name) for a in acceptance)]
        wants_lint = any(c.check is DeterministicCheck.LINT_CLEAN
                         for c in env.acceptance_criteria)
        passed = (pytest_run.exit_code == 0 and not missing
                  and (ruff_run.exit_code == 0 or not wants_lint))
        failed = [c.name for c in pytest_run.cases if c.outcome in ("failed", "error")]
        store.log_event(env.task_id, "checks_ran", passed=passed,
                        pytest_exit=pytest_run.exit_code, ruff_exit=ruff_run.exit_code,
                        failed=failed, missing_tests=missing,
                        cases=len(pytest_run.cases))
        return {"checks": [pytest_run.model_dump(), ruff_run.model_dump()],
                "missing": missing, "passed": passed}

    def adjudicate_node(state: CodeJoeState) -> dict:
        env = _envelope(ctx, state["task_id"])
        counters = LoopCounters(**state["counters"])
        counters.record_internal_iteration()
        pytest_run, ruff_run = (CommandRun(**c) for c in state["checks"])
        failed = [c for c in pytest_run.cases if c.outcome in ("failed", "error")]
        update: dict[str, Any] = {"counters": counters.model_dump()}
        report = _failure_report(pytest_run, ruff_run, failed, state["missing"])
        if counters.correction_cycles_used > 0:
            # After a REVISE the tests are frozen (D-004): only Builder may change anything.
            update.update(run_builder=True, run_tester=False, tester_feedback="",
                          builder_feedback="Checks still fail after Guardian's corrections. "
                                           f"Fix the code.\n\nFailing checks:\n{report}")
            store.log_event(env.task_id, "adjudicated", fault="code", by="rule",
                            reason="tests are frozen after REVISE")
            return update
        if not failed and pytest_run.exit_code == 0 and state["missing"]:
            # Only tests are missing: a known fix, no model call needed.
            update.update(run_builder=False, run_tester=True, builder_feedback="",
                          tester_feedback="Add tests for these criteria, named with their "
                          f"ids: {', '.join(state['missing'])}.")
            store.log_event(env.task_id, "adjudicated", fault="tests", by="rule",
                            reason="missing acceptance tests")
            return update
        gate = _Gate(ctx, state, "adjudicate")
        try:
            verdict, _ = adjudicate(gate.call, env, Plan(**state["plan"]),
                                    Path(state["worktree"]), report)
        except _STOPPING as e:
            return {"stopped": [f"adjudicate: {e}"], **gate.update()}
        fix_code = verdict.fault in ("code", "both")
        fix_tests = verdict.fault in ("tests", "both")
        store.log_event(env.task_id, "adjudicated", fault=verdict.fault, by="code_joe",
                        reason=verdict.reason[:500])
        update.update(run_builder=fix_code, run_tester=fix_tests,
                      builder_feedback=f"{verdict.builder_instructions}\n\nFailing checks:\n"
                                       f"{report}" if fix_code else "",
                      tester_feedback=verdict.tester_instructions if fix_tests else "",
                      **gate.update())
        return update

    def package_node(state: CodeJoeState) -> dict:
        env = _envelope(ctx, state["task_id"])
        wt = Worktree(repo=Path(env.project_ref).resolve(), path=Path(state["worktree"]),
                      branch=state["branch"], base_commit=state["base_commit"])
        sha = commit_all(wt, f"Code Joe: {env.description[:60]} ({env.task_id})")
        invs = store.invocations_for_task(env.task_id)
        tokens = TokenMetrics(
            input_tokens=sum(i.input_tokens for i in invs),
            output_tokens=sum(i.output_tokens for i in invs),
            cache_read_tokens=sum(i.cache_read_tokens for i in invs),
            cache_creation_tokens=sum(i.cache_creation_tokens for i in invs),
            estimated_cost_usd=store.spend_for_task(env.task_id))
        counters = LoopCounters(**state["counters"])
        plan = Plan(**state["plan"])
        issues = [f"no acceptance test for {m}" for m in state.get("missing", [])]
        if not state.get("passed"):
            issues.append("checks still failing after the iteration cap")
        result = StandardDepartmentResult(
            task_id=env.task_id, source_department=env.target_department,
            status=ResultStatus.COMPLETED if state.get("passed") else ResultStatus.PARTIAL,
            summary=plan.summary, worktree_path=str(wt.path), branch=wt.branch,
            changed_files=changed_files(wt), interface_spec=plan.interface,
            command_runs=[CommandRun(**c) for c in state["checks"]], tokens=tokens,
            model_call_count=len(invs), issues=issues,
            correction_cycles_used=counters.correction_cycles_used)
        store.record_result(result)
        store.set_task_status(env.task_id, TaskStatus.IN_REVIEW)
        store.log_event(env.task_id, "packaged", commit=sha, status=str(result.status),
                        changed_files=result.changed_files,
                        cost_usd=round(tokens.estimated_cost_usd, 6))
        return {"result": result.model_dump(mode="json")}

    def review_node(state: CodeJoeState) -> dict:
        env = _envelope(ctx, state["task_id"])
        result = StandardDepartmentResult.model_validate(state["result"])
        counters = LoopCounters(**state["counters"])
        t1 = run_tier1(env, result)
        results, findings = list(t1.criteria_results), list(t1.findings)
        pending, tier, update = frozenset(t1.pending_inspection), ReviewTier.DETERMINISTIC, {}
        summary = ""
        if t1.short_circuit:
            # Tier 1 already found a blocking problem: decide without a model call (D-007).
            corrections = _tier1_corrections(env, t1, result)
        else:
            gate = _Gate(ctx, state, "review")
            try:
                t2 = run_tier2(gate.call, env, result, t1.criteria_results,
                               t1.pending_inspection, state["base_commit"])
            except _STOPPING as e:
                return {"stopped": [f"review: {e}"], **gate.update()}
            results += t2.criteria_results
            findings += t2.findings
            pending, tier, corrections = frozenset(), ReviewTier.CHECKLIST, \
                t2.required_corrections
            summary, update = t2.summary, gate.update()
        review = build_review(
            task_id=env.task_id, source_department=Department.CODE_JOE, tier=tier,
            inp=VerdictInput(criteria=env.acceptance_criteria, criteria_results=results,
                             findings=findings, pending=pending,
                             correction_budget_left=counters.correction_budget_left()),
            required_corrections=corrections, summary=summary)
        store.record_review(review)
        store.log_event(env.task_id, "reviewed", tier=str(tier), verdict=str(review.verdict),
                        rule=review.matched_rule,
                        criteria={r.criterion_id: str(r.status) for r in results},
                        findings=[f"{f.severity}:{f.code}" for f in findings],
                        corrections=len(review.required_corrections))
        return {"review": review.model_dump(mode="json"), **update}

    def revise_node(state: CodeJoeState) -> dict:
        counters = LoopCounters(**state["counters"])
        counters.start_revision()  # consumes the task's one correction cycle (D-004)
        corrections = state["review"]["required_corrections"]
        store.set_task_status(state["task_id"], TaskStatus.RUNNING)
        store.log_event(state["task_id"], "revision_started", corrections=corrections)
        return {"counters": counters.model_dump(), "run_builder": True, "run_tester": False,
                "tester_feedback": "",
                "builder_feedback": "Guardian reviewed your work and sent it back. Fix "
                                    "these:\n" + "\n".join(f"- {c}" for c in corrections)}

    def deliver_node(state: CodeJoeState) -> dict:
        store.set_task_status(state["task_id"], TaskStatus.DONE)
        store.log_event(state["task_id"], "delivered", branch=state["branch"])
        return {"outcome": "passed"}

    def escalate_node(state: CodeJoeState) -> dict:
        store.set_task_status(state["task_id"], TaskStatus.ESCALATED)
        store.log_event(state["task_id"], "escalated",
                        reason=state["review"]["summary"][:500])
        return {"outcome": "escalated"}

    def finish_node(state: CodeJoeState) -> dict:
        task_id = state["task_id"]
        store.set_task_status(task_id, TaskStatus.FAILED)
        store.log_event(task_id, "code_joe_stopped", reasons=state.get("stopped", []))
        return {"outcome": "stopped"}

    def after_plan(state: CodeJoeState) -> Any:
        return "finish" if state.get("stopped") else ["builder", "tester"]

    def after_checks(state: CodeJoeState) -> str:
        if state.get("stopped"):
            return "finish"
        if state["passed"]:
            return "package"
        return ("adjudicate" if LoopCounters(**state["counters"]).can_iterate_internally()
                else "package")

    def after_review(state: CodeJoeState) -> str:
        if state.get("stopped"):
            return "finish"
        verdict = Verdict(state["review"]["verdict"])
        return {Verdict.PASS: "deliver", Verdict.REVISE: "revise"}.get(verdict, "escalate")

    def after_adjudicate(state: CodeJoeState) -> Any:
        if state.get("stopped"):
            return "finish"
        nxt = [n for n, on in (("builder", state["run_builder"]),
                               ("tester", state["run_tester"])) if on]
        return nxt or "checks"

    g = StateGraph(CodeJoeState)
    for name, fn in (("setup", setup), ("plan", plan_node), ("builder", builder_node),
                     ("tester", tester_node), ("checks", checks_node),
                     ("adjudicate", adjudicate_node), ("package", package_node),
                     ("review", review_node), ("revise", revise_node),
                     ("deliver", deliver_node), ("escalate", escalate_node),
                     ("finish", finish_node)):
        g.add_node(name, fn)
    g.add_edge(START, "setup")
    g.add_edge("setup", "plan")
    g.add_conditional_edges("plan", after_plan, ["builder", "tester", "finish"])
    g.add_edge("builder", "checks")
    g.add_edge("tester", "checks")
    g.add_conditional_edges("checks", after_checks, ["package", "adjudicate", "finish"])
    g.add_conditional_edges("adjudicate", after_adjudicate,
                            ["builder", "tester", "checks", "finish"])
    g.add_edge("package", "review")
    g.add_conditional_edges("review", after_review, ["deliver", "revise", "escalate", "finish"])
    g.add_edge("revise", "builder")
    g.add_edge("deliver", END)
    g.add_edge("escalate", END)
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)
