"""File-tool scopes, agent-loop safety rules, parallel budget reservations, store locking."""

import threading

import pytest
from fakes import FakeClient, message, tool_turn

from ezra.code_joe.tools import AgentError, FileTools, run_agent
from ezra.code_joe.workspace import Role
from ezra.config import load_limits, load_routing
from ezra.contracts import Department
from ezra.gateway import BudgetHold, Gateway
from ezra.pricing import load_pricing
from ezra.store import Store


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "wt"
    (r / "pkg").mkdir(parents=True)
    (r / "tests" / "acceptance").mkdir(parents=True)
    (r / "pkg" / "mod.py").write_text("x = 1\n")
    (r / "tests" / "test_old.py").write_text("def test_old(): pass\n")
    (r / "tests" / "acceptance" / "test_ac.py").write_text("def test_ac1(): pass\n")
    return r


def test_tester_reads_only_tests(root):
    t = FileTools(root, Role.TESTER)
    assert t.run("read_file", {"path": "tests/test_old.py"}) == ("def test_old(): pass\n", False)
    text, err = t.run("read_file", {"path": "pkg/mod.py"})
    assert err and "may not read" in text
    listing, _ = t.run("list_files", {"path": "."})
    assert "pkg/mod.py" not in listing and "tests/test_old.py" in listing


def test_builder_cannot_read_or_write_acceptance_tests(root):
    b = FileTools(root, Role.BUILDER)
    assert b.run("read_file", {"path": "tests/acceptance/test_ac.py"})[1]
    assert b.run("write_file", {"path": "tests/acceptance/x.py", "content": ""})[1]
    listing, _ = b.run("list_files", {"path": "."})
    assert "tests/acceptance" not in listing and "pkg/mod.py" in listing
    assert b.run("write_file", {"path": "pkg/new.py", "content": "y = 2\n"}) == \
        ("Wrote pkg/new.py (6 characters).", False)
    assert b.written == ["pkg/new.py"]


def test_bad_tool_input_is_an_error_result_not_a_crash(root):
    t = FileTools(root, Role.BUILDER)
    text, err = t.run("write_file", {"path": "pkg/a.py"})  # content missing
    assert err and "INVALID_JSON" in text
    assert t.run("rm_rf", {})[1]
    assert t.run("read_file", {"path": "../../etc/passwd"})[1]


@pytest.fixture
def gw(tmp_path):
    store = Store(tmp_path / "ezra.db")
    yield lambda replies: Gateway(store=store, routing=load_routing(), limits=load_limits(),
                                  pricing=load_pricing(), client=FakeClient(replies))
    store.close()


def agent(gateway, root, max_turns=3):
    return run_agent(gateway.call, operation="builder.implement",
                     department=Department.BUILDER, system="s", user="u",
                     tools=FileTools(root, Role.BUILDER), max_turns=max_turns,
                     max_tokens=1000, task_id="task_t")


def test_cut_off_turn_never_runs_its_tools(gw, root):
    g = gw([tool_turn(("write_file", {"path": "pkg/half.py", "content": "def f("}),
                      stop_reason="max_tokens"),
            message("ok")])
    run = agent(g, root)
    assert not (root / "pkg" / "half.py").exists() and run.summary == "ok"
    # messages: user, assistant, tool results
    results = g.client.messages.stream_calls[1]["messages"][2]["content"]
    assert results[0]["is_error"] and "cut off" in results[0]["content"]


def test_every_tool_call_gets_a_result_in_one_message(gw, root):
    g = gw([tool_turn(("read_file", {"path": "pkg/mod.py"}), ("list_files", {})),
            message("done")])
    agent(g, root)
    # messages: user, assistant, tool results
    results = g.client.messages.stream_calls[1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["tu_0_read_file", "tu_1_list_files"]
    assert g.client.messages.stream_calls[0]["cache_control"] == {"type": "ephemeral"}


def test_turn_cap(gw, root):
    g = gw([tool_turn(("list_files", {}))] * 3)
    with pytest.raises(AgentError, match="3-turn cap") as err:
        agent(g, root, max_turns=3)
    assert len(err.value.invocations) == 3


def test_parallel_calls_cannot_both_pass_one_budget(gw):
    g = gw([])
    # Two in-flight calls of $0.60 each under a $1.00 cap: the second must hold.
    g._check_and_reserve(task_id="task_p", operation="x", model="claude-sonnet-5-5",
                         worst=0.6, caps=(1.0, 10.0), approval_id=None, persist_hold=True)
    with pytest.raises(BudgetHold):
        g._check_and_reserve(task_id="task_p", operation="x", model="claude-sonnet-5-5",
                             worst=0.6, caps=(1.0, 10.0), approval_id="apr_fixed",
                             persist_hold=False)
    assert g.store.pending_approvals() == []  # the caller saves it when persist_hold=False
    g._release("task_p", 0.6)
    g._check_and_reserve(task_id="task_p", operation="x", model="claude-sonnet-5-5",
                         worst=0.6, caps=(1.0, 10.0), approval_id=None, persist_hold=True)


def test_store_is_safe_across_threads(tmp_path):
    store = Store(tmp_path / "t.db")
    threads = [threading.Thread(target=lambda n=n: [store.log_event("task_x", "e", n=n, i=i)
                                                    for i in range(50)]) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.events_for_task("task_x")) == 400
    store.close()
