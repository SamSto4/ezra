"""The progressive learning experiment harness. No network: real git, real pytest, a scripted
model."""

import json
import shutil

import pytest
from fakes import ScriptedClient, message, tool_turn

from ezra import experiment as ex
from ezra.code_joe.agents import BUILD_SYSTEM, PLAN_SYSTEM, TEST_SYSTEM
from ezra.config import LearningConfig, load_limits, load_routing
from ezra.gateway import Gateway
from ezra.guardian.tier2 import SYSTEM as GUARDIAN_SYSTEM
from ezra.pricing import load_pricing

TASKS = ex.load_tasks()


def test_task_set_is_balanced_and_well_formed():
    assert len(TASKS) >= 10
    assert {t.split for t in TASKS} == {"learn", "heldout"}
    # Split by category (§5.3): no category appears on both sides.
    learn = {t.category for t in TASKS if t.split == "learn"}
    held = {t.category for t in TASKS if t.split == "heldout"}
    assert learn and held and not learn & held
    assert len({t.id for t in TASKS}) == len(TASKS)


def test_every_section_has_learn_and_heldout_tasks():
    for section in ex.SECTIONS:
        splits = [t.split for t in TASKS if t.section == section]
        assert splits.count("learn") >= 2 and splits.count("heldout") >= 2, section


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_every_task_is_fair(task, tmp_path):
    check = ex.validate_task(task, tmp_path)
    assert check.ok, check.problems


def test_order_is_learn_first_and_seeded_by_run():
    for run in (1, 2):
        order = ex.order_tasks(TASKS, run)
        splits = [t.split for t in order]
        assert splits == sorted(splits, key=ex.SPLITS.index)
        assert [t.id for t in order] == [t.id for t in ex.order_tasks(TASKS, run)]
    assert [t.id for t in ex.order_tasks(TASKS, 1)] != [t.id for t in ex.order_tasks(TASKS, 2)]


def test_estimate_counts_reflections_only_for_the_lessons_arm():
    est = ex.estimate(TASKS, ["control", "lessons"], runs=2)
    learn = sum(t.split == "learn" for t in TASKS)
    assert est.task_runs == len(TASKS) * 4 and est.reflections == learn * 2
    assert est.low_usd < est.high_usd


def test_budget_matched_arm_gets_one_more_fix_round(tmp_path):
    limits = load_limits()
    env = ex.envelope(TASKS[0], tmp_path, limits, ex.ARMS["budget_matched"], 1.0, 10.0)
    assert env.counters.internal_iteration_cap == limits.internal_iteration_cap + 1


# -- a scripted run of one task --------------------------------------------------------------

WORD_COUNT = next(t for t in TASKS if t.id == "l04_fix_word_count")
FIXED = (WORD_COUNT.reference / "minitext" / "core.py").read_text()
BROKEN = FIXED.replace("return len(text.split())", 'return len(text.split(" "))')
PLAN = json.dumps({
    "summary": "Split on any whitespace.", "steps": ["Use str.split() with no argument"],
    "interface": [{"path": "minitext/core.py", "symbol": "word_count",
                   "signature": "word_count(text: str) -> int",
                   "description": "Counts whitespace-separated words."}],
    "test_file": "tests/acceptance/test_word_count.py"})
TESTS = ("from minitext import word_count\n\n\ndef test_ac1_empty_is_zero():\n"
         "    assert word_count('') == 0\n\n\ndef test_ac2_repeated_spaces():\n"
         "    assert word_count('a  b') == 2\n")
GUARDIAN_PASS = message(json.dumps({"criteria": [], "findings": [], "required_corrections": [],
                                    "summary": "ok"}), model="claude-opus-5-5")


def scripts(code):
    return {
        PLAN_SYSTEM: [message(PLAN)],
        BUILD_SYSTEM: [tool_turn(("write_file", {"path": "minitext/core.py", "content": code})),
                       message("done")],
        TEST_SYSTEM: [tool_turn(("write_file", {"path": "tests/acceptance/test_word_count.py",
                                                "content": TESTS})), message("done")],
        GUARDIAN_SYSTEM: [GUARDIAN_PASS],
    }


def factory(script):
    return lambda store: Gateway(store=store, routing=load_routing(), limits=load_limits(),
                                 pricing=load_pricing(), client=ScriptedClient(script))


def test_run_arm_grades_with_hidden_tests_and_records_rows(tmp_path):
    out = tmp_path / "results"
    rows = ex.run_arm("lessons", 1, [WORD_COUNT], max_usd=2.0, gateway_factory=factory(
        scripts(FIXED)), out_dir=out, learning=LearningConfig(memory="lessons"))
    (row,) = rows
    assert row.outcome == "passed" and row.verdict == "PASS" and row.memory == "lessons"
    assert row.hidden_pass and row.hidden_cases == 3 and row.hidden_failed == 0
    assert row.cost_usd > 0 and row.input_tokens > 0
    saved = ex.load_rows(out / "results.jsonl")
    assert saved[0]["task"] == "l04_fix_word_count" and saved[0]["hidden_pass"] is True
    # The hidden tests were removed again: Ezra's worktree never keeps them.
    assert not list((out / "lessons-r1" / "wt").rglob("test_hidden_*.py"))
    with pytest.raises(ex.core.RunError):  # an arm and run never start twice on old data
        ex.run_arm("lessons", 1, [WORD_COUNT], max_usd=2.0, out_dir=out)


def test_hidden_tests_catch_what_the_visible_tests_miss(tmp_path):
    # Ezra's own acceptance tests pass on code that still miscounts tabs and newlines...
    half_fixed = BROKEN.replace('return len(text.split(" "))',
                                'return len([w for w in text.split(" ") if w])')
    (row,) = ex.run_arm("control", 1, [WORD_COUNT], max_usd=2.0,
                        gateway_factory=factory(scripts(half_fixed)), out_dir=tmp_path)
    # ...so Guardian may PASS it, but the hidden tests decide true success.
    assert row.verdict == "PASS" and not row.hidden_pass and row.hidden_failed >= 1


def test_spend_cap_stops_before_a_task_that_cannot_fit(tmp_path):
    rows = ex.run_arm("control", 1, [WORD_COUNT], max_usd=0.01,
                      gateway_factory=factory(scripts(FIXED)), out_dir=tmp_path)
    assert rows == []


# -- report ----------------------------------------------------------------------------------


def _rows():
    rows = []
    for run in (1, 2):
        for i in range(5):
            for arm, win in (("control", i < 2), ("lessons", i < 4)):
                rows.append(dict(arm=arm, run=run, task=f"t{i}", split="heldout",
                                 hidden_pass=win, verdict="PASS", cost_usd=0.05))
    return rows


def test_summary_and_paired_difference():
    rows = _rows()
    s = ex.summarize(rows)
    assert s["control"]["success_rate"] == 0.4 and s["lessons"]["success_rate"] == 0.8
    assert s["lessons"]["cost_per_success_usd"] == pytest.approx(0.0625)
    d = ex.paired_difference(rows, "lessons")
    assert d["pairs"] == 10 and d["diff"] == pytest.approx(0.4)
    assert d["ci_low"] <= 0.4 <= d["ci_high"]
    assert ex.paired_difference(rows, "budget_matched") is None


def test_summary_by_section():
    rows = _rows()
    for r in rows:
        r["section"] = "plan" if r["task"] in ("t0", "t1") else "test"
    plan = ex.summarize(rows, split=None, section="plan")
    assert plan["control"]["success_rate"] == 1.0 and plan["control"]["n"] == 4
    assert ex.summarize(rows, section="review") == {}


def test_cli_cap_covers_the_whole_command(monkeypatch, capsys):
    from ezra import cli
    caps = []

    def fake_run_arm(arm, run, tasks, max_usd, on_task=None):
        caps.append(round(max_usd, 2))
        return [ex.Row(arm=arm, run=run, task="t", category="bug_fix", split="learn",
                       section="test", memory="off", task_id="x", outcome="passed",
                       verdict="PASS", reviews=1, hidden_pass=True, hidden_cases=1,
                       hidden_failed=0, cost_usd=0.4, input_tokens=1, output_tokens=1,
                       cache_read_tokens=0, lessons_used=[], lessons_added=[])]

    monkeypatch.setattr(ex, "run_arm", fake_run_arm)
    assert cli.main(["experiment", "run", "--runs", "2", "--sections", "test",
                     "--max-usd", "1", "--confirm"]) == cli.EXIT_OK
    # Each arm gets what's left of the one cap, and the loop stops once it's used up.
    assert caps == [1.0, 0.6, 0.2]
    assert "Spent $1.2000 of the $1.00 cap" in capsys.readouterr().out
    assert cli.main(["experiment", "estimate", "--sections", "nope"]) == cli.EXIT_ERROR


def test_cli_estimate_and_run_needs_confirmation(capsys):
    from ezra import cli
    assert cli.main(["experiment", "estimate", "--runs", "1"]) == cli.EXIT_OK
    assert "task runs" in capsys.readouterr().out
    assert cli.main(["experiment", "run", "--max-usd", "5"]) == cli.EXIT_HOLD
    assert "Nothing was run" in capsys.readouterr().out


def test_fixture_is_never_modified_by_a_run(tmp_path):
    before = {p.relative_to(ex.EXPERIMENT_DIR): p.read_bytes()
              for p in (ex.EXPERIMENT_DIR / "fixture").rglob("*") if p.is_file()
              and "__pycache__" not in p.parts}
    ex.run_arm("control", 1, [WORD_COUNT], max_usd=2.0,
               gateway_factory=factory(scripts(FIXED)), out_dir=tmp_path)
    after = {p.relative_to(ex.EXPERIMENT_DIR): p.read_bytes()
             for p in (ex.EXPERIMENT_DIR / "fixture").rglob("*") if p.is_file()
             and "__pycache__" not in p.parts}
    assert before == after
    shutil.rmtree(tmp_path)
