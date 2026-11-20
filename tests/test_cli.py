"""The CLI is a thin client: it calls ezra.core and prints."""

import pytest
from fakes import FakeClient
from test_intake import decision

from ezra import cli, core
from ezra.contracts import Department, ModelInvocation
from ezra.store import Store


@pytest.fixture
def wire(tmp_path, monkeypatch, git_repo):
    db = tmp_path / "ezra.db"

    def _wire(*replies):
        client = FakeClient(list(replies))
        monkeypatch.setattr(core, "open_store", lambda: Store(db))
        real_open_gateway, real_ask = core.open_gateway, core.ask
        monkeypatch.setattr(core, "open_gateway", lambda store: real_open_gateway(store, client))
        monkeypatch.setattr(core, "ask", lambda gw, req: real_ask(gw, req, project=git_repo))
        return db
    return _wire


def test_direct_answer_prints_answer_and_cost(wire, capsys):
    wire(decision("direct"))
    assert cli.main(["ask", "what's", "2+2"]) == cli.EXIT_OK
    out, err = capsys.readouterr()
    assert out.strip() == "4"
    # 900 in * $2 + 150 out * $10, per million (Sonnet 5.5)
    assert "[direct] claude-sonnet-5-5 · in 900 · out 150" in err and "$0.003300" in err


def test_code_request_prints_task_and_task_command_shows_it(wire, capsys):
    wire(decision())
    assert cli.main(["ask", "add", "sentence_count"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Created task task_" in out and "AC1 [critical · test]" in out
    assert "AC3 [major · deterministic:tests_pass]" in out
    task_id = out.split("Created task ")[1].split()[0]
    assert cli.main(["task", task_id]) == cli.EXIT_OK
    shown = capsys.readouterr().out
    assert "[created]" in shown and "intake_routed" in shown


def test_unknown_task(wire, capsys):
    wire()
    assert cli.main(["task", "task_nope"]) == cli.EXIT_ERROR


def test_hold_exits_2_and_lists_approval(wire, capsys):
    db = wire(decision("direct"))
    s = Store(db)
    s.record_invocation(ModelInvocation(task_id=None, operation_id="ezra.intake",
                                        department=Department.EZRA, operation_type="intake",
                                        model_id="claude-sonnet-5-5", actual_cost_usd=10.0))
    s.close()
    assert cli.main(["ask", "hi"]) == cli.EXIT_HOLD
    assert "HOLD" in capsys.readouterr().err
    assert cli.main(["approvals"]) == cli.EXIT_OK
    assert "budget_hold" in capsys.readouterr().out
