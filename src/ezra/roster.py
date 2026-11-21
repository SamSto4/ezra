"""The agent roster (M7 UI): who does what in Ezra, and how each agent has performed.

Static facts (role, operations, what each agent may touch) live here in one place; the
numbers come from the store, so viewing the roster never calls a model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ezra.config import load_routing
from ezra.store import Store


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    department: str
    role: str
    operations: tuple[str, ...]
    can: tuple[str, ...]
    cannot: tuple[str, ...]


ROSTER: tuple[AgentSpec, ...] = (
    AgentSpec(
        id="intake", name="Ezra intake", department="Ezra",
        role="Reads your request and routes it: answer directly, create a coding task with "
             "acceptance criteria, or explain it isn't supported yet.",
        operations=("ezra.intake",),
        can=("Answer questions", "Write 2–8 typed acceptance criteria", "Create a task"),
        cannot=("Touch any code", "Run anything")),
    AgentSpec(
        id="code_joe", name="Code Joe", department="Code Joe",
        role="Leads the coding department: plans the change with an interface spec, and when "
             "checks fail, judges whether the code or the tests are wrong.",
        operations=("code_joe.plan", "code_joe.adjudicate"),
        can=("Plan steps and the interface spec", "Send work back to Builder or Tester"),
        cannot=("Write code or tests", "Approve its own work")),
    AgentSpec(
        id="builder", name="Builder", department="Code Joe",
        role="Implements the plan in the task's own git worktree using file tools.",
        operations=("builder.implement",),
        can=("Read and write project files", "Fix what Guardian sends back"),
        cannot=("Read or write tests/acceptance/", "Change test config (D-015)",
                "Run commands")),
    AgentSpec(
        id="tester", name="Tester", department="Code Joe",
        role="Writes acceptance tests from the criteria and the interface spec, without "
             "seeing Builder's code.",
        operations=("tester.write_tests",),
        can=("Write the acceptance test file", "Read tests/ for style"),
        cannot=("Read the implementation", "Run commands")),
    AgentSpec(
        id="guardian", name="Guardian", department="Guardian",
        role="Independent reviewer. Tier 1 checks are deterministic and free; Tier 2 judges "
             "the diff against the criteria. The verdict always comes from the D-002 table.",
        operations=("guardian.tier2",),
        can=("Judge inspection criteria with evidence", "Report findings and corrections"),
        cannot=("Edit code", "See Builder's conversation", "Pick the verdict itself")),
    AgentSpec(
        id="learner", name="Learner", department="Learner",
        role="Looks back at finished tasks and distills short lessons for next time. A lesson "
             "is only kept after a check, and one that keeps hurting is retired on its own.",
        operations=("learner.reflect",),
        can=("Propose lessons from Guardian's outcomes", "Rate whether used lessons helped"),
        cannot=("Change Guardian's rules", "Give lessons to Guardian",
                "Keep a lesson that fails its check")),
)


# The D-002 verdict table in plain words (rows as in guardian/verdict.py; first match wins).
_RULES = (
    ("HOLD", "An authorization or permission question is unresolved."),
    ("ESCALATE", "A finding can't be fixed safely without you."),
    ("REVISE", "A critical criterion is unmet, and a correction cycle is left."),
    ("ESCALATE", "A critical criterion is unmet, and no correction cycle is left."),
    ("REVISE", "The quality grade is FAIL (Tier 3 only), with a cycle left."),
    ("ESCALATE", "The quality grade is FAIL (Tier 3 only), no cycle left."),
    ("REVISE", "A major criterion or finding is unmet, with a cycle left."),
    ("ESCALATE", "A major criterion or finding is unmet, no cycle left."),
    ("PASS", "Every critical and major requirement is met. Minor issues become notes."),
)
VERDICT_RULES: tuple[dict[str, Any], ...] = tuple(
    {"rule": i, "verdict": v, "when": w} for i, (v, w) in enumerate(_RULES, 1))


@dataclass
class OperationStats:
    operation: str
    model: str
    effort: str
    calls: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    tasks: int = 0
    last_at: str | None = None
    prompt_versions: list[str] = field(default_factory=list)


def agent_stats(store: Store) -> list[dict[str, Any]]:
    routing = load_routing()
    rows = {r["operation_id"]: r for r in store.invocation_stats()}
    versions = store.prompt_versions()
    reviews = store.review_counts()
    events = store.event_counts()
    out = []
    for spec in ROSTER:
        ops = []
        for op in spec.operations:
            route = routing.operations.get(op)
            st = OperationStats(operation=op, model=route.model if route else "?",
                                effort=route.effort if route else "?")
            r = rows.get(op)
            if r:
                for k in ("calls", "failures", "input_tokens", "output_tokens",
                          "cache_read_tokens", "cache_creation_tokens", "latency_ms", "tasks"):
                    setattr(st, k, int(r[k] or 0))
                st.cost_usd, st.last_at = float(r["cost_usd"] or 0.0), r["last_at"]
            st.prompt_versions = versions.get(op, [])
            ops.append(st)
        calls = sum(o.calls for o in ops)
        input_side = sum(o.input_tokens + o.cache_read_tokens + o.cache_creation_tokens
                         for o in ops)
        extra: dict[str, Any] = {}
        if spec.id == "guardian":
            extra = {"verdicts": {k: v for k, v in reviews.items() if not k.startswith("_")},
                     "tier1_only": reviews.get("_tier1", 0)}
        elif spec.id == "code_joe":
            extra = {"plans": events.get("plan_ready", 0),
                     "adjudications": events.get("adjudicated", 0)}
        elif spec.id == "builder":
            extra = {"runs": events.get("builder_done", 0),
                     "revisions": events.get("revision_started", 0)}
        elif spec.id == "tester":
            extra = {"runs": events.get("tester_done", 0)}
        elif spec.id == "intake":
            extra = {"routed": events.get("intake_routed", 0)}
        elif spec.id == "learner":
            from ezra.config import load_learning
            from ezra.contracts import LessonStatus
            extra = {"lessons_active": len(store.lessons(LessonStatus.ACTIVE)),
                     "lessons_total": len(store.lessons()),
                     "learned_from": events.get("lessons_learned", 0),
                     "memory": load_learning().memory}
        out.append({
            **asdict(spec), "operations": [asdict(o) for o in ops], "calls": calls,
            "cost_usd": sum(o.cost_usd for o in ops),
            "cache_share": (sum(o.cache_read_tokens for o in ops) / input_side
                            if input_side else 0.0),
            "last_at": max((o.last_at for o in ops if o.last_at), default=None),
            "tasks": max((o.tasks for o in ops), default=0),
            **extra})
    return out


def system_view(store: Store) -> dict[str, Any]:
    """Routing, limits, prices, the verdict table, decisions and cache savings: how Ezra is
    configured right now, read-only (changing any of it is a D-009 Level 1 decision)."""
    from ezra.config import CONFIG_DIR, PROJECT_ROOT, load_limits
    from ezra.pricing import load_pricing

    routing, limits, pricing = load_routing(), load_limits(), load_pricing()
    agent_of = {op: spec.id for spec in ROSTER for op in spec.operations}
    saved = 0.0
    for r in store.cache_reads_by_model():
        p = pricing.get(r["model_id"])
        if p:
            saved += (r["cache_read_tokens"] or 0) * (p.input - p.cache_read) / 1_000_000
    decisions = []
    path = PROJECT_ROOT / "docs" / "decisions.md"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3 and cells[0].startswith("D-0"):
                decisions.append({"id": cells[0], "title": cells[1].replace("**", ""),
                                  "status": cells[2]})
    return {
        "routing_version": routing.version,
        "routing": [{"operation": op, "model": r.model, "effort": r.effort,
                     "agent": agent_of.get(op)} for op, r in routing.operations.items()],
        "limits": limits.model_dump(),
        "prices": {m: {"input": p.input, "output": p.output, "cache_read": p.cache_read,
                       "cache_write": p.cache_write}
                   for m, p in pricing.models.items() if m in {r.model for r in
                                                               routing.operations.values()}},
        "verdict_rules": list(VERDICT_RULES),
        "decisions": decisions,
        "cache_saved_usd": round(saved, 6),
        "config_dir": str(CONFIG_DIR.relative_to(PROJECT_ROOT)),
    }
