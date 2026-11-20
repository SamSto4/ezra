"""Model Gateway: request shape, cost accounting, budget HOLD, failure logging."""

from datetime import UTC, datetime, timedelta

import anthropic
import pytest
from fakes import FakeClient, attempt, message

from ezra.config import load_limits, load_routing
from ezra.contracts import ApprovalStatus, Department, ModelInvocation
from ezra.gateway import BudgetHold, Gateway, GatewayError, ModelRefusal
from ezra.pricing import load_pricing
from ezra.store import Store

NOW = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "ezra.db")
    yield s
    s.close()


def gateway(store, client, now=NOW):
    return Gateway(store=store, routing=load_routing(), limits=load_limits(),
                   pricing=load_pricing(), client=client, now=lambda: now)


def call(gw, operation="ezra.intake", task_id=None, max_tokens=1000):
    return gw.call(operation=operation, department=Department.EZRA, system="You are Ezra.",
                   messages=[{"role": "user", "content": "2+2?"}], max_tokens=max_tokens,
                   task_id=task_id)


def kinds(store, task_id=None):
    rows = store.conn.execute("SELECT kind FROM events WHERE task_id IS ? ORDER BY id",
                              (task_id,)).fetchall()
    return [r["kind"] for r in rows]


def only_invocation(store):
    rows = store.conn.execute("SELECT record FROM model_invocations").fetchall()
    assert len(rows) == 1
    return ModelInvocation.model_validate_json(rows[0]["record"])


def test_request_shape(store):
    client = FakeClient()
    call(gateway(store, client))
    sent = client.messages.stream_calls[0]
    assert sent["model"] == "claude-sonnet-5-5"
    assert sent["output_config"] == {"effort": "medium"}
    assert sent["thinking"] == {"type": "adaptive"}
    assert sent["fallbacks"] == "default"
    assert sent["betas"] == ["server-side-fallback-2026-07-01"]
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    counted = client.messages.count_calls[0]
    assert "fallbacks" not in counted and "max_tokens" not in counted


def test_success_records_tokens_cost_and_events(store):
    reply = message("Four.", input_tokens=1000, output_tokens=200, cache_read=3000,
                    cache_write=600)
    resp = call(gateway(store, FakeClient([reply])))
    assert resp.text == "Four."  # the thinking block is skipped
    inv = only_invocation(store)
    assert (inv.input_tokens, inv.output_tokens, inv.cache_read_tokens,
            inv.cache_creation_tokens) == (1000, 200, 3000, 600)
    # sonnet-5-5: 1000*2 + 200*10 + 3000*0.10 + 600*2.50, per million
    assert inv.actual_cost_usd == pytest.approx(0.0058)
    assert inv.estimated_cost_usd > inv.actual_cost_usd
    assert inv.request_id == "req_fake123" and inv.success
    assert kinds(store) == ["model_call_started", "model_call_finished"]


def test_fallback_attempts_priced_at_their_own_models(store):
    reply = message("Plan.", model="claude-opus-5", iterations=[
        attempt("claude-opus-5-5", input_tokens=500, output_tokens=0),
        attempt("claude-opus-5", kind="fallback_message", input_tokens=500, output_tokens=100),
    ])
    call(gateway(store, FakeClient([reply])), operation="code_joe.plan")
    inv = only_invocation(store)
    assert inv.requested_model == "claude-opus-5-5" and inv.model_id == "claude-opus-5"
    assert inv.fallback_used
    assert inv.input_tokens == 1000 and inv.output_tokens == 100
    assert inv.actual_cost_usd == pytest.approx(500 * 4e-6 + 500 * 5e-6 + 100 * 25e-6)


def test_unpriced_served_model_never_counts_as_free(store):
    reply = message(model="claude-mystery", iterations=[attempt("claude-mystery")])
    call(gateway(store, FakeClient([reply])), task_id="task_x")
    inv = only_invocation(store)
    assert inv.actual_cost_usd is None and inv.estimated_cost_usd > 0
    assert store.spend_for_task("task_x") == pytest.approx(inv.estimated_cost_usd)
    assert "unpriced_model" in kinds(store, "task_x")


def test_refusal_is_recorded_then_raised(store):
    reply = message("", stop_reason="refusal", stop_details=type("D", (), {"category": "cyber"}))
    with pytest.raises(ModelRefusal):
        call(gateway(store, FakeClient([reply])))
    inv = only_invocation(store)
    assert not inv.success and inv.failure_reason == "refusal:cyber"


def test_api_error_is_recorded_then_raised(store):
    err = anthropic.APIConnectionError(message="network down", request=None)
    with pytest.raises(GatewayError):
        call(gateway(store, FakeClient([err])))
    inv = only_invocation(store)
    assert not inv.success and inv.failure_reason.startswith("APIConnectionError")
    assert kinds(store)[-1] == "model_call_finished"


def test_truncated_answer_is_flagged(store):
    resp = call(gateway(store, FakeClient([message("Half an ans", stop_reason="max_tokens")])))
    assert resp.truncated and only_invocation(store).success


def test_count_failure_still_checks_budget_with_a_high_estimate(store):
    client = FakeClient(count_error=anthropic.APIConnectionError(message="x", request=None))
    call(gateway(store, client))
    started = [e for e in store.events_for_task(None) if e["kind"] == "model_call_started"][0]
    assert started["counted_input_tokens"] > 0


def _spend(store, usd, *, task_id=None, at=NOW):
    store.record_invocation(ModelInvocation(
        task_id=task_id, operation_id="ezra.intake", department=Department.EZRA,
        operation_type="intake", model_id="claude-sonnet-5-5", actual_cost_usd=usd,
        created_at=at))


def test_task_budget_hold_stops_before_the_model(store):
    _spend(store, 1.999, task_id="task_x")
    client = FakeClient()
    with pytest.raises(BudgetHold) as hold:
        call(gateway(store, client), task_id="task_x")
    assert client.messages.stream_calls == []  # nothing was sent
    pending = store.pending_approvals()
    assert [p.approval_id for p in pending] == [hold.value.approval.approval_id]
    assert pending[0].level == 1 and pending[0].kind == "budget_hold"
    assert "task budget" in pending[0].summary
    assert "budget_hold" in kinds(store, "task_x")


def test_daily_budget_counts_only_today(store):
    _spend(store, 9.999, at=NOW - timedelta(days=1))  # yesterday: ignored
    call(gateway(store, FakeClient()))
    _spend(store, 9.999)  # today
    with pytest.raises(BudgetHold) as hold:
        call(gateway(store, FakeClient()))
    assert "daily budget" in hold.value.approval.summary


def test_call_without_task_is_capped_by_the_task_budget(store):
    # 1M output tokens on Sonnet could cost $10: over the $2 per-task cap.
    with pytest.raises(BudgetHold):
        call(gateway(store, FakeClient()), max_tokens=1_000_000)


def test_approval_can_be_resolved_once(store):
    _spend(store, 1.999, task_id="task_x")
    with pytest.raises(BudgetHold) as hold:
        call(gateway(store, FakeClient()), task_id="task_x")
    aid = hold.value.approval.approval_id
    rec = store.resolve_approval(aid, approved=True, response="ok, continue")
    assert rec.status is ApprovalStatus.APPROVED and rec.resolved_at
    assert store.pending_approvals() == []
    with pytest.raises(ValueError):
        store.resolve_approval(aid, approved=False)


def test_gateway_refuses_to_start_with_an_unpriced_routed_model(store):
    routing = load_routing()
    routing.operations["ezra.intake"].model = "claude-unknown"
    with pytest.raises(KeyError):
        Gateway(store=store, routing=routing, limits=load_limits(), pricing=load_pricing(),
                client=FakeClient())


def test_worst_case_uses_the_priciest_fallback():
    p = load_pricing()
    # opus-5-5 can fall back to opus-5 / opus-4-8 ($6.25 cache write, $25 output)
    assert p.worst_case("claude-opus-5-5", input_tokens=1000, max_tokens=1000) == \
        pytest.approx((1000 * 6.25 + 1000 * 25) / 1e6)


def test_api_key_never_reaches_the_database(tmp_path, store):
    # A real SDK client pointed at a closed local port: both the count and the call fail.
    sentinel = "sk-ant-api03-SENTINEL-DO-NOT-STORE"
    client = anthropic.Anthropic(api_key=sentinel, base_url="http://127.0.0.1:9",
                                 max_retries=0, timeout=2)
    with pytest.raises(GatewayError):
        call(gateway(store, client))
    store.close()
    assert sentinel.encode() not in (tmp_path / "ezra.db").read_bytes()


def _status_error(code):
    import httpx2
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIStatusError(f"error {code}", response=httpx2.Response(code, request=req),
                                    body=None)


def test_rejected_call_books_no_spend(store):
    with pytest.raises(GatewayError):
        call(gateway(store, FakeClient([_status_error(400)])), task_id="task_x")
    assert only_invocation(store).actual_cost_usd == 0.0
    assert store.spend_for_task("task_x") == 0.0


def test_ambiguous_failure_keeps_the_worst_case_as_spend(store):
    err = anthropic.APIConnectionError(message="dropped", request=None)
    with pytest.raises(GatewayError):
        call(gateway(store, FakeClient([err])), task_id="task_x")
    expected = only_invocation(store).estimated_cost_usd
    assert store.spend_for_task("task_x") == pytest.approx(expected)


def test_missing_credentials_is_a_clear_error(store, monkeypatch):
    from ezra.gateway import MissingCredentials
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(store.path.parent))  # no `ant auth login` profile either
    with pytest.raises(MissingCredentials):
        Gateway(store=store, routing=load_routing(), limits=load_limits(),
                pricing=load_pricing())
