"""The progressive learning experiment (docs/research/progressive-learning.md §5).

Does Ezra with lessons beat Ezra without them, per token, on tasks it has never seen?

- Tasks live in experiments/progressive-learning/tasks/<id>/: task.yaml (what Ezra is told),
  hidden/ (tests Ezra never sees; they decide true success) and reference/ (a known-good
  solution, used only to check that the hidden tests are fair).
- Every task runs on a fresh git copy of the fixture project, so tasks are independent and
  only lessons can carry anything from one task to the next.
- Arms differ by configuration only, never by code path:
    control         no lessons
    lessons         learn on the "learn" tasks, then use the lessons frozen on "heldout"
    budget_matched  no lessons, one extra fix round instead (the Hajimiri et al. control)
- Each arm and run gets its own database, so lessons never leak between arms.
- Spend is capped by --max-usd across the whole call: each task's cap is the smaller of the
  usual task budget and what's left, so the Gateway's own HOLD rules enforce the total.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ezra import core
from ezra.code_joe.sandbox import run_pytest
from ezra.config import DATA_DIR, PROJECT_ROOT, LearningConfig, load_learning, load_limits
from ezra.contracts import (
    AcceptanceCriterion,
    Budget,
    CommandRun,
    Department,
    Limits,
    LoopCounters,
    TaskEnvelope,
)
from ezra.store import Store

EXPERIMENT_DIR = PROJECT_ROOT / "experiments" / "progressive-learning"
RESULTS_DIR = DATA_DIR / "experiments" / "progressive-learning"
SPLITS = ("learn", "heldout")
CATEGORIES = ("new_function", "bug_fix", "docs", "edge_case", "refactor")
# Measured in M4/M5: a coding task costs about $0.05-0.07; a reflection about $0.005-0.01.
TASK_COST_RANGE = (0.05, 0.10)
REFLECT_COST = 0.01
_IDENT = ["-c", "user.name=ezra-experiment", "-c", "user.email=experiment@localhost"]


@dataclass(frozen=True)
class Arm:
    name: str
    learn_memory: str  # memory mode on "learn" tasks
    heldout_memory: str  # memory mode on "heldout" tasks
    extra_iterations: int = 0  # extra internal fix rounds (budget-matched control)


ARMS = {
    "control": Arm("control", "off", "off"),
    "lessons": Arm("lessons", "lessons", "frozen"),
    "budget_matched": Arm("budget_matched", "off", "off", extra_iterations=1),
}


@dataclass
class TaskSpec:
    id: str
    category: str
    split: str
    description: str
    criteria: list[AcceptanceCriterion]
    constraints: list[str]
    path: Path

    @property
    def hidden_tests(self) -> list[Path]:
        return sorted((self.path / "hidden").glob("test_*.py"))

    @property
    def reference(self) -> Path:
        return self.path / "reference"


def load_tasks(base: Path = EXPERIMENT_DIR) -> list[TaskSpec]:
    tasks = []
    for tdir in sorted((base / "tasks").iterdir()):
        if not (tdir / "task.yaml").exists():
            continue
        meta = yaml.safe_load((tdir / "task.yaml").read_text())
        if meta["split"] not in SPLITS or meta["category"] not in CATEGORIES:
            raise ValueError(f"{tdir.name}: bad split or category")
        tasks.append(TaskSpec(
            id=meta["id"], category=meta["category"], split=meta["split"],
            description=meta["description"],
            criteria=[AcceptanceCriterion.model_validate(c) for c in meta["criteria"]],
            constraints=meta.get("constraints", []), path=tdir))
    return tasks


def make_project(fixture: Path, dest: Path, overlay: Path | None = None) -> Path:
    """A fresh git repo holding the fixture, optionally with the reference files on top."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(fixture, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    if overlay is not None:
        shutil.copytree(overlay, dest, dirs_exist_ok=True)
    for cmd in (["init", "-q"], ["add", "-A"], [*_IDENT, "commit", "-q", "-m", "fixture"]):
        subprocess.run(["git", *cmd], cwd=dest, check=True, capture_output=True)
    return dest


def run_hidden(project: Path, task: TaskSpec, timeout: int) -> CommandRun:
    """Run the task's hidden tests in `project`, then remove them again."""
    target = project / "tests" / "hidden"
    target.mkdir(parents=True, exist_ok=True)
    rels = []
    for src in task.hidden_tests:
        shutil.copy(src, target / src.name)
        rels.append(f"tests/hidden/{src.name}")
    try:
        return run_pytest(project, timeout, paths=rels)
    finally:
        shutil.rmtree(target, ignore_errors=True)


# -- task validation (no model calls) ----------------------------------------------------


@dataclass
class TaskCheck:
    task_id: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def validate_task(task: TaskSpec, workdir: Path, base: Path = EXPERIMENT_DIR,
                  timeout: int = 120) -> TaskCheck:
    """A fair task: the hidden tests fail on the untouched fixture, and the reference
    solution passes both the hidden tests and the fixture's own tests."""
    check = TaskCheck(task.id)
    fixture = base / "fixture"
    if not task.hidden_tests:
        check.problems.append("no hidden tests")
        return check
    if not task.reference.exists():
        check.problems.append("no reference solution")
        return check
    before = make_project(fixture, workdir / task.id / "before")
    if run_hidden(before, task, timeout).exit_code == 0:
        check.problems.append("hidden tests already pass on the fixture")
    after = make_project(fixture, workdir / task.id / "after", overlay=task.reference)
    hidden = run_hidden(after, task, timeout)
    if hidden.exit_code != 0:
        failing = [c.name for c in hidden.cases if c.outcome != "passed"]
        check.problems.append(f"reference fails hidden tests: {failing or hidden.output_excerpt}")
    own = run_pytest(after, timeout)
    if own.exit_code != 0:
        check.problems.append("reference breaks the fixture's own tests")
    for c in task.criteria:
        for hidden_file in task.hidden_tests:
            if c.id.lower() in hidden_file.read_text().lower():
                check.problems.append(f"hidden tests mention {c.id}; they must stay unseen")
    return check


# -- planning and cost -------------------------------------------------------------------


def order_tasks(tasks: list[TaskSpec], run: int) -> list[TaskSpec]:
    """Learn tasks first, then held-out ones; each shuffled with the run as the seed, so
    every arm sees the same order within a run and a different order across runs."""
    rng = random.Random(run)
    out = []
    for split in SPLITS:
        group = [t for t in tasks if t.split == split]
        rng.shuffle(group)
        out += group
    return out


@dataclass
class Estimate:
    task_runs: int
    reflections: int
    low_usd: float
    high_usd: float


def estimate(tasks: list[TaskSpec], arms: list[str], runs: int) -> Estimate:
    n = len(tasks) * len(arms) * runs
    reflections = sum(1 for t in tasks if t.split == "learn") * runs * \
        sum(1 for a in arms if ARMS[a].learn_memory == "lessons")
    low = n * TASK_COST_RANGE[0] + reflections * REFLECT_COST
    high = n * TASK_COST_RANGE[1] + reflections * REFLECT_COST
    return Estimate(n, reflections, round(low, 2), round(high, 2))


# -- running -------------------------------------------------------------------------------


def envelope(task: TaskSpec, project: Path, limits: Limits, arm: Arm,
             task_cap: float, daily_cap: float) -> TaskEnvelope:
    counters = LoopCounters.from_limits(limits)
    counters.internal_iteration_cap += arm.extra_iterations
    return TaskEnvelope(
        target_department=Department.CODE_JOE, description=task.description,
        project_ref=str(project), acceptance_criteria=task.criteria,
        constraints=task.constraints, counters=counters,
        budget=Budget(task_limit_usd=task_cap, daily_limit_usd=daily_cap))


@dataclass
class Row:
    arm: str
    run: int
    task: str
    category: str
    split: str
    memory: str
    task_id: str
    outcome: str
    verdict: str | None
    reviews: int
    hidden_pass: bool
    hidden_cases: int
    hidden_failed: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    lessons_used: list[str]
    lessons_added: list[str]
    error: str | None = None


def run_arm(arm_name: str, run: int, tasks: list[TaskSpec], max_usd: float,
            gateway_factory: Callable[[Store], Any] = core.open_gateway,
            base: Path = EXPERIMENT_DIR, out_dir: Path = RESULTS_DIR,
            limits: Limits | None = None, learning: LearningConfig | None = None,
            on_task: Callable[[Row], None] | None = None) -> list[Row]:
    """Run one arm once over the tasks, in this run's order, never spending past max_usd."""
    arm = ARMS[arm_name]
    limits = limits or load_limits()
    learning = learning or load_learning()
    data = out_dir / f"{arm_name}-r{run}"
    if data.exists():
        raise core.RunError(f"{data} already exists: each arm and run starts from nothing. "
                            "Move it away to run it again.")
    data.mkdir(parents=True)
    store = Store(data / "ezra.db")
    rows: list[Row] = []
    spent = 0.0
    try:
        gateway = gateway_factory(store)
        for task in order_tasks(tasks, run):
            remaining = max_usd - spent
            if remaining < TASK_COST_RANGE[0]:
                break  # not enough left for even a cheap task
            memory = arm.learn_memory if task.split == "learn" else arm.heldout_memory
            project = make_project(base / "fixture", data / "projects" / task.id)
            env = envelope(task, project, limits, arm,
                           task_cap=min(limits.task_budget_usd, remaining),
                           daily_cap=max(limits.daily_budget_usd, max_usd))
            store.save_task(env)
            error = None
            try:
                out = core.run_task(store, gateway, env.task_id, memory=memory,
                                    learning=learning, checkpoint_path=data / "cp.db",
                                    worktrees_dir=data / "wt")
            except core.RunError as e:  # recorded as a failed task, never silently skipped
                out, error = None, str(e)
            hidden = None
            if out is not None and out.result is not None and out.result.worktree_path:
                hidden = run_hidden(Path(out.result.worktree_path), task,
                                    limits.test_timeout_seconds)
            invs = store.invocations_for_task(env.task_id)
            cost = store.spend_for_task(env.task_id)
            spent += cost
            row = Row(
                arm=arm_name, run=run, task=task.id, category=task.category,
                split=task.split, memory=memory, task_id=env.task_id,
                outcome=out.outcome if out else "error",
                verdict=str(out.review.verdict) if out and out.review else None,
                reviews=out.reviews if out else 0,
                hidden_pass=bool(hidden and hidden.exit_code == 0),
                hidden_cases=len(hidden.cases) if hidden else 0,
                hidden_failed=sum(c.outcome != "passed" for c in hidden.cases) if hidden else 0,
                cost_usd=round(cost, 6),
                input_tokens=sum(i.input_tokens for i in invs),
                output_tokens=sum(i.output_tokens for i in invs),
                cache_read_tokens=sum(i.cache_read_tokens for i in invs),
                lessons_used=store.lessons_used_by_task(env.task_id),
                lessons_added=(out.learning.added if out and out.learning else []),
                error=error)
            rows.append(row)
            out_dir.mkdir(parents=True, exist_ok=True)
            with (out_dir / "results.jsonl").open("a") as f:
                f.write(json.dumps(asdict(row)) + "\n")
            if on_task:
                on_task(row)
    finally:
        store.close()
    return rows


# -- report ------------------------------------------------------------------------------


def load_rows(path: Path = RESULTS_DIR / "results.jsonl") -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize(rows: list[dict[str, Any]], split: str = "heldout") -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for arm in sorted({r["arm"] for r in rows}):
        rs = [r for r in rows if r["arm"] == arm and r["split"] == split]
        if not rs:
            continue
        wins = sum(r["hidden_pass"] for r in rs)
        cost = sum(r["cost_usd"] for r in rs)
        out[arm] = dict(n=len(rs), runs=len({r["run"] for r in rs}),
                        success_rate=wins / len(rs),
                        guardian_pass_rate=sum(r["verdict"] == "PASS" for r in rs) / len(rs),
                        mean_cost_usd=cost / len(rs),
                        cost_per_success_usd=(cost / wins) if wins else None)
    return out


def paired_difference(rows: list[dict[str, Any]], arm: str, baseline: str = "control",
                      split: str = "heldout", resamples: int = 5000,
                      seed: int = 0) -> dict[str, float] | None:
    """Success-rate difference (arm minus baseline) on tasks both ran, paired by run and
    task, with a 95% percentile bootstrap interval. None if there are no pairs."""
    def key(r):
        return (r["run"], r["task"])
    a = {key(r): r["hidden_pass"] for r in rows if r["arm"] == arm and r["split"] == split}
    b = {key(r): r["hidden_pass"] for r in rows if r["arm"] == baseline and r["split"] == split}
    pairs = [(int(a[k]), int(b[k])) for k in sorted(a.keys() & b.keys())]
    if not pairs:
        return None
    diffs = [x - y for x, y in pairs]
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs)
                   for _ in range(resamples))
    return dict(pairs=len(pairs), diff=sum(diffs) / len(diffs),
                ci_low=boots[int(0.025 * resamples)], ci_high=boots[int(0.975 * resamples) - 1])
