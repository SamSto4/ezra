"""The intake A/B (docs/benchmarks.md, Tuning v2 item 6): the example switch and the runner.

No network: every model reply comes from FakeClient."""

import json

import pytest
from fakes import FakeClient
from test_intake import decision

from ezra import cli, core
from ezra.benchmarks import intake_ab as ab
from ezra.benchmarks.reference import example
from ezra.config import load_limits, load_routing
from ezra.gateway import Gateway
from ezra.intake import SYSTEM_PROMPT, run_intake, system_prompt
from ezra.pricing import load_pricing
from ezra.store import Store


def _gateway(store, replies):
    client = FakeClient(replies)
    gw = Gateway(store=store, routing=load_routing(), limits=load_limits(),
                 pricing=load_pricing(), client=client)
    return gw, client


def test_default_prompt_is_unchanged_and_the_example_is_opt_in():
    assert system_prompt() == SYSTEM_PROMPT
    with_example = system_prompt(with_example=True)
    assert with_example.startswith(SYSTEM_PROMPT)
    assert example("acceptance-criteria/best").body in with_example
    assert system_prompt(True) == with_example  # static, so it caches


def test_intake_sends_the_example_only_when_asked(tmp_path, git_repo):
    store = Store(tmp_path / "ezra.db")
    try:
        gw, client = _gateway(store, [decision(), decision()])
        run_intake(gw, "Add f", project=git_repo, limits=load_limits())
        run_intake(gw, "Add f", project=git_repo, limits=load_limits(), with_example=True)
    finally:
        store.close()
    first, second = client.messages.stream_calls
    assert first["system"][0]["text"] == SYSTEM_PROMPT
    assert second["system"][0]["text"] == system_prompt(True)


def test_run_arm_records_one_row_per_request(tmp_path, git_repo):
    replies = [decision(), decision("direct")]
    seen = []
    rows = ab.run_arm("example", 1, [("t1", "Add f"), ("t2", "what's 2+2")], git_repo,
                      max_usd=1.0, out_dir=tmp_path / "out",
                      gateway_factory=lambda store: _gateway(store, replies)[0],
                      on_row=seen.append)
    assert [r.task for r in rows] == ["t1", "t2"] and seen == rows
    code, direct = rows
    assert code.route == "code" and code.repairs == 0 and code.criteria == 3
    assert code.model_criteria == 2 and code.cost_usd > 0
    assert direct.route == "direct" and direct.criteria == 0
    saved = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text()
             .splitlines()]
    assert [r["arm"] for r in saved] == ["example", "example"]


def test_run_arm_stops_before_the_cap(tmp_path, git_repo):
    rows = ab.run_arm("control", 1, [("t1", "Add f")], git_repo, max_usd=0.01,
                      out_dir=tmp_path / "out",
                      gateway_factory=lambda store: _gateway(store, [])[0])
    assert rows == []


def test_run_arm_never_reuses_a_finished_arm(tmp_path, git_repo):
    (tmp_path / "out" / "control-r1").mkdir(parents=True)
    with pytest.raises(core.RunError):
        ab.run_arm("control", 1, [], git_repo, max_usd=1.0, out_dir=tmp_path / "out")


def test_summary_compares_the_arms():
    def row(arm, criteria, repairs=0):
        return {"arm": arm, "run": 1, "route": "code", "criteria": criteria,
                "model_criteria": criteria - 1, "warnings": [], "repairs": repairs,
                "output_tokens": 100 * criteria, "cost_usd": 0.01, "error": None}
    s = ab.summarize([row("control", 8), row("control", 6, repairs=1), row("example", 5)])
    assert s["control"]["mean_criteria"] == 7 and s["control"]["repair_rate"] == 0.5
    assert s["example"]["mean_model_criteria"] == 4 and s["example"]["calls"] == 1


def test_cli_estimates_and_wont_spend_without_confirm(capsys):
    assert cli.main(["intake-ab", "estimate"]) == cli.EXIT_OK
    assert "60 intake calls" in capsys.readouterr().out
    assert cli.main(["intake-ab", "run", "--max-usd", "1"]) == cli.EXIT_HOLD
    assert "Nothing was run" in capsys.readouterr().out
