"""The CLI is a thin client: it calls ezra.core and prints."""

import pytest
from fakes import FakeClient, message

from ezra import cli, core
from ezra.contracts import Department, ModelInvocation
from ezra.store import Store


@pytest.fixture
def wired(tmp_path, monkeypatch):
    db = tmp_path / "ezra.db"
    client = FakeClient([message("Four.", input_tokens=33, output_tokens=5)])
    monkeypatch.setattr(core, "open_store", lambda: Store(db))
    real_open_gateway = core.open_gateway
    monkeypatch.setattr(core, "open_gateway", lambda store: real_open_gateway(store, client))
    return db


def test_ask_prints_answer_and_cost(wired, capsys):
    assert cli.main(["ask", "what's", "2+2"]) == cli.EXIT_OK
    out, err = capsys.readouterr()
    assert out.strip() == "Four."
    assert "claude-sonnet-5-5 · in 33 · out 5" in err and "$0.000116" in err


def test_ask_on_hold_exits_2_and_lists_approval(wired, capsys):
    s = Store(wired)
    s.record_invocation(ModelInvocation(task_id=None, operation_id="ezra.intake",
                                        department=Department.EZRA, operation_type="intake",
                                        model_id="claude-sonnet-5-5", actual_cost_usd=10.0))
    s.close()
    assert cli.main(["ask", "hi"]) == cli.EXIT_HOLD
    assert "HOLD" in capsys.readouterr().err
    assert cli.main(["approvals"]) == cli.EXIT_OK
    assert "budget_hold" in capsys.readouterr().out
