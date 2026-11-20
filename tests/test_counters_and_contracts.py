"""D-004 loop counters and contract validation."""

import pytest
from pydantic import ValidationError

from ezra.config import load_limits, load_routing
from ezra.contracts import (
    AcceptanceCriterion,
    DeterministicCheck,
    LoopCounters,
    LoopLimitError,
    Severity,
    Verification,
)


def test_internal_iterations_capped_at_two_before_submission():
    c = LoopCounters()
    c.record_internal_iteration()
    c.record_internal_iteration()
    assert not c.can_iterate_internally()
    with pytest.raises(LoopLimitError):
        c.record_internal_iteration()


def test_revision_consumes_the_single_correction_and_resets_iterations_to_cap_one():
    c = LoopCounters()
    c.record_internal_iteration()
    c.record_internal_iteration()
    c.start_revision()
    assert c.correction_cycles_used == 1
    assert c.internal_iterations_used == 0 and c.internal_iteration_cap == 1
    c.record_internal_iteration()
    assert not c.can_iterate_internally()


def test_second_revision_is_refused():
    c = LoopCounters()
    c.start_revision()
    assert not c.correction_budget_left()
    with pytest.raises(LoopLimitError):
        c.start_revision()


def test_internal_iterations_do_not_touch_correction_budget():
    c = LoopCounters()
    c.record_internal_iteration()
    c.record_internal_iteration()
    assert c.correction_budget_left()


def test_counters_follow_configured_limits():
    c = LoopCounters.from_limits(load_limits())
    assert (c.internal_iteration_cap, c.correction_cycle_limit) == (2, 1)


def test_routing_table_loads_and_rejects_unknown_operation():
    table = load_routing()
    assert table.route("code_joe.plan").model == "claude-opus-5-5"
    with pytest.raises(KeyError):
        table.route("nope")


def test_deterministic_criterion_requires_check():
    with pytest.raises(ValidationError):
        AcceptanceCriterion(id="AC1", text="t", severity=Severity.MAJOR,
                            verification=Verification.DETERMINISTIC)
    with pytest.raises(ValidationError):
        AcceptanceCriterion(id="AC1", text="t", severity=Severity.MAJOR,
                            verification=Verification.TEST, check=DeterministicCheck.LINT_CLEAN)


def test_criterion_id_format_enforced():
    with pytest.raises(ValidationError):
        AcceptanceCriterion(id="criterion-1", text="t", severity=Severity.MAJOR,
                            verification=Verification.TEST)


def test_contracts_reject_unknown_fields():
    with pytest.raises(ValidationError):
        LoopCounters(surprise=1)
