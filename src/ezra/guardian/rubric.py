"""Quality Rubric grading with gates instead of an average threshold (D-003).

The rubric itself (weights, gates, anchors, critical failures, agent checks) lives in
config/rubric.yaml and is versioned (D-014). Used by Tier 3 reviews (not in Phase 1's live flow)
and later by Model Evals. It is pure code, so it's built and tested now.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ezra.config import CONFIG_DIR
from ezra.contracts import Department, Finding, QualityGrade, Severity


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Category(_Strict):
    name: str
    weight: float = Field(gt=0, le=1)
    core: bool
    measures: str
    excludes: str


class Gates(_Strict):
    core_fail_max: int = Field(ge=1, le=5)
    core_pass_min: int = Field(ge=1, le=5)
    other_pass_min: int = Field(ge=1, le=5)
    excellent_min_score: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> Gates:
        if self.core_fail_max >= self.core_pass_min:
            raise ValueError("core_fail_max must be below core_pass_min")
        return self


class AgentCheck(_Strict):
    id: str
    severity: Severity
    check: str


class Rubric(_Strict):
    version: str
    date: str
    scale: dict[int, str]
    categories: dict[str, Category]
    gates: Gates
    critical_failures: dict[str, str]
    agent_checks: dict[Department, list[AgentCheck]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_date(cls, data):
        if isinstance(data, dict) and "date" in data:
            data = {**data, "date": str(data["date"])}
        return data

    @model_validator(mode="after")
    def _consistent(self) -> Rubric:
        if set(self.scale) != {1, 2, 3, 4, 5}:
            raise ValueError("scale must describe exactly the scores 1-5")
        total = sum(c.weight for c in self.categories.values())
        if not math.isclose(total, 1.0, abs_tol=1e-9):
            raise ValueError(f"category weights must sum to 1.0, got {total}")
        if not any(c.core for c in self.categories.values()):
            raise ValueError("at least one category must be core")
        ids = [c.id for checks in self.agent_checks.values() for c in checks]
        if len(ids) != len(set(ids)):
            raise ValueError("agent check ids must be unique")
        return self

    @property
    def core(self) -> tuple[str, ...]:
        return tuple(k for k, c in self.categories.items() if c.core)


class RubricGrade(_Strict):
    grade: QualityGrade
    weighted_score: float
    rubric_version: str
    critical_failures: tuple[str, ...] = ()


def load_rubric(config_dir: Path = CONFIG_DIR) -> Rubric:
    with (config_dir / "rubric.yaml").open() as f:
        return Rubric.model_validate(yaml.safe_load(f) or {})


@cache
def default_rubric() -> Rubric:
    return load_rubric()


def weighted_score(scores: Mapping[str, int], rubric: Rubric | None = None) -> float:
    """Spec formula: sum(weight x rating / 5) x 100. Kept for trends and Model Evals, not gating."""
    rubric = rubric or default_rubric()
    _validate(scores, rubric)
    return round(sum(c.weight * scores[k] / 5 for k, c in rubric.categories.items()) * 100, 2)


def grade(scores: Mapping[str, int], critical_failures: Iterable[str] = (),
          rubric: Rubric | None = None) -> RubricGrade:
    rubric = rubric or default_rubric()
    criticals = tuple(critical_failures)
    unknown = sorted(set(criticals) - set(rubric.critical_failures))
    if unknown:
        raise ValueError(f"unknown critical failure codes: {unknown}")
    score = weighted_score(scores, rubric)
    g = rubric.gates
    core = rubric.core
    others = [k for k in rubric.categories if k not in core]
    if criticals or any(scores[k] <= g.core_fail_max for k in core):
        result = QualityGrade.FAIL
    elif any(scores[k] < g.core_pass_min for k in core) or any(
            scores[k] < g.other_pass_min for k in others):
        result = QualityGrade.CONDITIONAL
    elif score >= g.excellent_min_score:
        result = QualityGrade.EXCELLENT
    else:
        result = QualityGrade.PASS
    return RubricGrade(grade=result, weighted_score=score, rubric_version=rubric.version,
                       critical_failures=criticals)


def agent_check_findings(department: Department, results: Mapping[str, bool],
                         rubric: Rubric | None = None) -> list[Finding]:
    """Turn a department's yes/no agent checks into Findings for the verdict table.

    A check with no result counts as failed: unverifiable counts as unmet (D-002).
    """
    rubric = rubric or default_rubric()
    checks = rubric.agent_checks.get(department, [])
    unknown = sorted(set(results) - {c.id for c in checks})
    if unknown:
        raise ValueError(f"unknown agent checks for {department}: {unknown}")
    findings = []
    for c in checks:
        passed = results.get(c.id)
        if passed is True:
            continue
        why = "failed" if passed is False else "could not be verified"
        findings.append(Finding(code=f"agent_check:{c.id}", severity=c.severity,
                                message=f"{c.check} ({why})"))
    return findings


def _validate(scores: Mapping[str, int], rubric: Rubric) -> None:
    if set(scores) != set(rubric.categories):
        raise ValueError(f"scores must have exactly these categories: {sorted(rubric.categories)}")
    bad = {k: v for k, v in scores.items()
           if not (isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 5)}
    if bad:
        raise ValueError(f"scores must be integers 1-5: {bad}")
