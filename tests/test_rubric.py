"""D-003 gate-based grading."""

import pytest

from ezra.contracts import QualityGrade
from ezra.guardian.rubric import WEIGHTS, grade, weighted_score


def scores(default=4, **overrides):
    s = dict.fromkeys(WEIGHTS, default)
    s.update(overrides)
    return s


def test_all_fours_scores_80_and_now_passes():
    # The problem D-003 fixed: under the old 85 threshold this was "conditional".
    assert weighted_score(scores(4)) == 80.0
    assert grade(scores(4), False) == (QualityGrade.PASS, 80.0)


def test_excellent_needs_pass_gates_and_90():
    assert grade(scores(5), False)[0] is QualityGrade.EXCELLENT
    assert grade(scores(5, F_clarity=3, G_presentation=3), False)[0] is QualityGrade.EXCELLENT


def test_core_category_at_3_is_conditional_even_if_rest_are_5():
    assert grade(scores(5, A_accuracy=3), False)[0] is QualityGrade.CONDITIONAL


def test_non_core_at_2_is_conditional():
    assert grade(scores(4, G_presentation=2), False)[0] is QualityGrade.CONDITIONAL


def test_core_at_2_fails():
    assert grade(scores(5, C_task_achievement=2), False)[0] is QualityGrade.FAIL


def test_critical_failure_fails_regardless_of_score():
    assert grade(scores(5), True)[0] is QualityGrade.FAIL


def test_presentation_cannot_rescue_weak_core():
    s = scores(5, B_instruction_adherence=3)
    assert weighted_score(s) >= 90 and grade(s, False)[0] is QualityGrade.CONDITIONAL


@pytest.mark.parametrize("bad", [scores(6), scores(0), {"A_accuracy": 4}])
def test_invalid_scores_rejected(bad):
    with pytest.raises(ValueError):
        grade(bad, False)
