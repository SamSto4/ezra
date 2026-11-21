"""Intake A/B: does showing intake the best criteria example make its criteria leaner?

Approved 2026-11-21 (docs/benchmarks.md, "Tuning v2", item 6). Intake-only: no coding task
runs, so a call costs about $0.01. The requests are the progressive-learning pilot's task
descriptions, reused so the two experiments share one task set.

    arm "control"  today's intake system prompt
    arm "example"  the same prompt plus the best example from
                   docs/reference-outputs/acceptance-criteria.md (~600 tokens, cached)

Measured per call: repairs (model calls - 1), route, criteria (all, and excluding the free
deterministic checks), benchmark warnings, tokens and cost. Adopt the example only if criteria
and output tokens go down with no rise in repairs. Each arm and run gets its own database.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from ezra import core
from ezra.config import DATA_DIR
from ezra.contracts import new_id
from ezra.gateway import BudgetHold, GatewayError
from ezra.intake import IntakeError, run_intake
from ezra.store import Store

ARMS = {"control": False, "example": True}
RESULTS_DIR = DATA_DIR / "experiments" / "intake-example"
# Measured on 6 real coding intakes (2026-11-20/21): about $0.012 a call with a cold cache.
# Back to back the system prompt is a cache read, so the expected cost is lower; this is the
# careful number. One repair would double a call.
CALL_COST_USD = 0.012
# Stop before a call when less than this is left under --max-usd (a call plus one repair).
CALL_RESERVE_USD = 0.03


@dataclass
class Row:
    arm: str
    run: int
    task: str
    request_id: str
    route: str | None
    model_calls: int
    repairs: int
    criteria: int
    model_criteria: int
    warnings: list[str]
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    error: str | None = None


def estimate(n_requests: int, arms: list[str], runs: int) -> tuple[int, float]:
    calls = n_requests * len(arms) * runs
    return calls, round(calls * CALL_COST_USD, 2)


def run_arm(arm: str, run: int, requests: list[tuple[str, str]], project: Path,
            max_usd: float, out_dir: Path = RESULTS_DIR,
            gateway_factory: Callable[[Store], Any] = core.open_gateway,
            on_row: Callable[[Row], None] | None = None) -> list[Row]:
    """Send every (task id, request) through intake once, never spending past max_usd."""
    data = out_dir / f"{arm}-r{run}"
    if data.exists():
        raise core.RunError(f"{data} already exists: each arm and run starts from nothing. "
                            "Move it away to run it again.")
    data.mkdir(parents=True)
    store = Store(data / "ezra.db")
    rows: list[Row] = []
    spent = 0.0
    try:
        gateway = gateway_factory(store)
        for task_id, request in requests:
            if max_usd - spent < CALL_RESERVE_USD:
                break
            error, result = None, None
            request_id = new_id("task")
            try:
                result = run_intake(gateway, request, project=project, limits=gateway.limits,
                                    request_id=request_id, with_example=ARMS[arm])
            except (IntakeError, GatewayError, BudgetHold) as e:  # recorded, never skipped
                error = f"{type(e).__name__}: {e}"
            invs = store.invocations_for_task(request_id)
            bench = [e for e in store.events_for_task(request_id)
                     if e["kind"] == "intake_benchmark"]
            metrics = bench[0].get("metrics", {}) if bench else {}
            cost = sum(i.actual_cost_usd or 0.0 for i in invs)
            spent += cost
            row = Row(arm=arm, run=run, task=task_id, request_id=request_id,
                      route=str(result.route) if result else None,
                      model_calls=len(invs), repairs=max(len(invs) - 1, 0),
                      criteria=metrics.get("criteria", 0),
                      model_criteria=metrics.get("model_criteria", 0),
                      warnings=bench[0].get("warnings", []) if bench else [],
                      input_tokens=sum(i.input_tokens for i in invs),
                      output_tokens=sum(i.output_tokens for i in invs),
                      cache_read_tokens=sum(i.cache_read_tokens for i in invs),
                      cache_write_tokens=sum(i.cache_creation_tokens for i in invs),
                      cost_usd=round(cost, 6), error=error)
            rows.append(row)
            with (out_dir / "results.jsonl").open("a") as f:
                f.write(json.dumps(asdict(row)) + "\n")
            if on_row:
                on_row(row)
    finally:
        store.close()
    return rows


def load_rows(path: Path = RESULTS_DIR / "results.jsonl") -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        if not rs:
            continue
        code = [r for r in rs if r["route"] == "code"]
        out[arm] = {
            "calls": len(rs),
            "runs": len({r["run"] for r in rs}),
            "errors": sum(r["error"] is not None for r in rs),
            "repair_rate": sum(r["repairs"] > 0 for r in rs) / len(rs),
            "code_routes": len(code),
            "mean_criteria": mean(r["criteria"] for r in code) if code else None,
            "mean_model_criteria": mean(r["model_criteria"] for r in code) if code else None,
            "mean_warnings": mean(len(r["warnings"]) for r in code) if code else None,
            "mean_output_tokens": mean(r["output_tokens"] for r in rs),
            "mean_cost_usd": mean(r["cost_usd"] for r in rs),
            "total_cost_usd": sum(r["cost_usd"] for r in rs),
        }
    return out
