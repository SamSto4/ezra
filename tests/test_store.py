"""SQLite store round trips and spend accounting."""

from datetime import timedelta

from conftest import envelope

from ezra.contracts import (
    Department,
    GuardianReview,
    ModelInvocation,
    ResultStatus,
    ReviewTier,
    StandardDepartmentResult,
    TaskStatus,
    Verdict,
    utcnow,
)
from ezra.store import Store


def inv(task_id, est=None, actual=None, when=None):
    return ModelInvocation(task_id=task_id, operation_id="op", department=Department.BUILDER,
                           operation_type="builder.implement", model_id="claude-sonnet-5-5",
                           input_tokens=100, output_tokens=50, estimated_cost_usd=est,
                           actual_cost_usd=actual, created_at=when or utcnow())


def test_task_round_trip_and_status(tmp_path):
    s = Store(tmp_path / "ezra.db")
    env = envelope([])
    s.save_task(env)
    s.set_task_status(env.task_id, TaskStatus.RUNNING)
    got, status = s.get_task(env.task_id)
    assert got == env and status is TaskStatus.RUNNING
    assert s.get_task("missing") is None


def test_spend_prefers_actual_over_estimate(tmp_path):
    s = Store(":memory:")
    s.record_invocation(inv("t1", est=0.10))
    s.record_invocation(inv("t1", est=0.50, actual=0.20))
    s.record_invocation(inv("t2", est=1.00))
    assert round(s.spend_for_task("t1"), 6) == 0.30
    assert len(s.invocations_for_task("t1")) == 2


def test_daily_spend_window():
    s = Store(":memory:")
    s.record_invocation(inv("t1", est=5.0, when=utcnow() - timedelta(days=2)))
    s.record_invocation(inv("t1", est=1.5))
    assert s.spend_since(utcnow() - timedelta(days=1)) == 1.5


def test_results_reviews_and_events():
    s = Store(":memory:")
    r = StandardDepartmentResult(task_id="t1", source_department=Department.CODE_JOE,
                                 status=ResultStatus.COMPLETED, summary="ok")
    s.record_result(r)
    rv = GuardianReview(task_id="t1", source_department=Department.CODE_JOE,
                        tier=ReviewTier.DETERMINISTIC, verdict=Verdict.PASS, matched_rule=9)
    s.record_review(rv)
    s.log_event("t1", "plan.created", steps=3)
    s.log_event("t1", "builder.done", files=["a.py"])
    assert s.results_for_task("t1") == [r]
    assert s.reviews_for_task("t1") == [rv]
    assert [e["kind"] for e in s.events_for_task("t1")] == ["plan.created", "builder.done"]
    assert s.events_for_task("t1")[1]["files"] == ["a.py"]
