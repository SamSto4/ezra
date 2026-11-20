"""Quality Rubric grading with gates instead of an average threshold (D-003).

Used by Tier 3 reviews (not in Phase 1's live flow) and later by Model Evals. It is pure code,
so it's built and tested now.
"""

from __future__ import annotations

from ezra.contracts import QualityGrade

WEIGHTS: dict[str, float] = {
    "A_accuracy": 0.20,
    "B_instruction_adherence": 0.20,
    "C_task_achievement": 0.20,
    "D_context_awareness": 0.15,
    "E_reasoning": 0.15,
    "F_clarity": 0.05,
    "G_presentation": 0.05,
}
CORE = ("A_accuracy", "B_instruction_adherence", "C_task_achievement")


def weighted_score(scores: dict[str, int]) -> float:
    """Spec formula: sum(weight x rating / 5) x 100. Kept for trends, not for gating."""
    _validate(scores)
    return round(sum(WEIGHTS[k] * scores[k] / 5 for k in WEIGHTS) * 100, 2)


def grade(scores: dict[str, int], has_critical_failure: bool) -> tuple[QualityGrade, float]:
    _validate(scores)
    score = weighted_score(scores)
    others = [k for k in WEIGHTS if k not in CORE]
    if has_critical_failure or any(scores[k] <= 2 for k in CORE):
        return QualityGrade.FAIL, score
    if any(scores[k] == 3 for k in CORE) or any(scores[k] <= 2 for k in others):
        return QualityGrade.CONDITIONAL, score
    if score >= 90:
        return QualityGrade.EXCELLENT, score
    return QualityGrade.PASS, score


def _validate(scores: dict[str, int]) -> None:
    if set(scores) != set(WEIGHTS):
        raise ValueError(f"scores must have exactly these categories: {sorted(WEIGHTS)}")
    bad = {k: v for k, v in scores.items() if not (isinstance(v, int) and 1 <= v <= 5)}
    if bad:
        raise ValueError(f"scores must be integers 1-5: {bad}")
