"""D-003 gate-based grading with the versioned rubric config (D-014)."""

import pytest
import yaml

from ezra.config import CONFIG_DIR
from ezra.contracts import Department, QualityGrade, Severity
from ezra.guardian.rubric import (
    Rubric,
    agent_check_findings,
    default_rubric,
    grade,
    load_rubric,
    weighted_score,
)

RUBRIC = default_rubric()


def scores(default=4, **overrides):
    s = dict.fromkeys(RUBRIC.categories, default)
    s.update(overrides)
    return s


def raw_config():
    return yaml.safe_load((CONFIG_DIR / "rubric.yaml").read_text())


# --- The shipped config -------------------------------------------------------

def test_v1_weights_reasoning_up_context_down():
    weights = {k: c.weight for k, c in RUBRIC.categories.items()}
    assert RUBRIC.version == "1"
    assert weights == {
        "A_accuracy": 0.20, "B_instruction_adherence": 0.20, "C_task_achievement": 0.20,
        "D_context_awareness": 0.10, "E_reasoning": 0.20, "F_clarity": 0.05,
        "G_presentation": 0.05,
    }
    assert RUBRIC.core == ("A_accuracy", "B_instruction_adherence", "C_task_achievement")


def test_every_agent_has_checks():
    assert set(RUBRIC.agent_checks) == set(Department)


# --- D-003 gates --------------------------------------------------------------

def test_all_fours_scores_80_and_passes():
    # The problem D-003 fixed: under the old 85 threshold this was "conditional".
    g = grade(scores(4))
    assert (g.grade, g.weighted_score, g.rubric_version) == (QualityGrade.PASS, 80.0, "1")


def test_excellent_needs_pass_gates_and_90():
    assert grade(scores(5)).grade is QualityGrade.EXCELLENT
    assert grade(scores(5, F_clarity=3, G_presentation=3)).grade is QualityGrade.EXCELLENT


def test_core_category_at_3_is_conditional_even_if_rest_are_5():
    assert grade(scores(5, A_accuracy=3)).grade is QualityGrade.CONDITIONAL


def test_non_core_at_2_is_conditional():
    assert grade(scores(4, G_presentation=2)).grade is QualityGrade.CONDITIONAL


def test_reasoning_is_not_core():
    # Weight went up in v1, but a 3 in Reasoning still passes the gates.
    assert grade(scores(4, E_reasoning=3)).grade is QualityGrade.PASS


def test_core_at_2_fails():
    assert grade(scores(5, C_task_achievement=2)).grade is QualityGrade.FAIL


def test_critical_failure_fails_regardless_of_score():
    g = grade(scores(5), ["fabrication"])
    assert g.grade is QualityGrade.FAIL and g.critical_failures == ("fabrication",)


def test_unknown_critical_failure_code_rejected():
    with pytest.raises(ValueError, match="unknown critical failure"):
        grade(scores(5), ["looked_wrong"])


def test_presentation_cannot_rescue_weak_core():
    s = scores(5, B_instruction_adherence=3)
    assert weighted_score(s) >= 90 and grade(s).grade is QualityGrade.CONDITIONAL


@pytest.mark.parametrize("bad", [scores(6), scores(0), scores(True), {"A_accuracy": 4}])
def test_invalid_scores_rejected(bad):
    with pytest.raises(ValueError):
        grade(bad)


# --- Config validation --------------------------------------------------------

def test_weights_must_sum_to_one():
    cfg = raw_config()
    cfg["categories"]["E_reasoning"]["weight"] = 0.25
    with pytest.raises(ValueError, match="sum to 1.0"):
        Rubric.model_validate(cfg)


def test_gates_must_be_ordered():
    cfg = raw_config()
    cfg["gates"]["core_fail_max"] = 4
    with pytest.raises(ValueError, match="core_fail_max"):
        Rubric.model_validate(cfg)


def test_unknown_field_rejected():
    cfg = raw_config()
    cfg["threshold"] = 85
    with pytest.raises(ValueError):
        Rubric.model_validate(cfg)


def test_alternate_rubric_version_can_be_used(tmp_path):
    cfg = raw_config()
    cfg["version"] = "test"
    cfg["gates"]["excellent_min_score"] = 80
    (tmp_path / "rubric.yaml").write_text(yaml.safe_dump(cfg))
    g = grade(scores(4), rubric=load_rubric(tmp_path))
    assert (g.grade, g.rubric_version) == (QualityGrade.EXCELLENT, "test")


# --- Agent checks become findings ---------------------------------------------

def test_passed_checks_give_no_findings():
    ids = [c.id for c in RUBRIC.agent_checks[Department.BUILDER]]
    assert agent_check_findings(Department.BUILDER, dict.fromkeys(ids, True)) == []


def test_failed_and_missing_checks_become_findings_at_their_severity():
    findings = agent_check_findings(Department.BUILDER, {"BLD-1": False, "BLD-2": True})
    by_code = {f.code: f for f in findings}
    assert set(by_code) == {"agent_check:BLD-1", "agent_check:BLD-3"}
    assert by_code["agent_check:BLD-1"].severity is Severity.CRITICAL
    assert "could not be verified" in by_code["agent_check:BLD-3"].message


def test_check_from_another_agent_rejected():
    with pytest.raises(ValueError, match="unknown agent checks"):
        agent_check_findings(Department.BUILDER, {"TST-1": True})
