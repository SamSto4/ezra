"""Benchmarks: the reference outputs are loaded as data and every agent output kind is scored
against them. The reference files and the scorers are held to each other here: a best example
must pass cleanly, a weak one must be caught for the reasons its file gives."""

import json

import pytest
from fakes import FakeClient
from test_intake import decision

from ezra import cli
from ezra.benchmarks import load_examples, score
from ezra.benchmarks.reference import ReferenceError, example
from ezra.benchmarks.scorers import (
    score_criteria,
    score_eval,
    score_review,
    score_standard,
    template_fields,
)
from ezra.config import load_limits, load_routing
from ezra.gateway import Gateway
from ezra.intake import run_intake
from ezra.pricing import load_pricing
from ezra.store import Store

EXAMPLES = load_examples()


def body(example_id: str) -> str:
    return example(example_id).body


# -- the reference files themselves ---------------------------------------------------


def test_every_reference_file_has_a_best_and_a_weak_example():
    kinds = {}
    for e in EXAMPLES:
        kinds.setdefault(e.kind, set()).add(e.label)
    assert set(kinds) == {"acceptance-criteria", "standards", "model-evals", "quality-rubric"}
    for labels in kinds.values():
        assert "best" in labels and "weak" in labels
    assert {"best-review", "weak-review"} <= kinds["quality-rubric"]


@pytest.mark.parametrize("ex", [e for e in EXAMPLES if e.expected_to_pass], ids=lambda e: e.id)
def test_best_examples_pass_cleanly(ex):
    s = score(ex.scorer, ex.body)
    assert s.gates == [] and s.warnings == []


@pytest.mark.parametrize("ex", [e for e in EXAMPLES if not e.expected_to_pass],
                         ids=lambda e: e.id)
def test_weak_examples_are_caught(ex):
    assert not score(ex.scorer, ex.body).clean


def test_loader_rejects_a_marker_without_a_block(tmp_path):
    (tmp_path / "standards.md").write_text("<!-- example: standards/best -->\nno fence\n")
    with pytest.raises(ReferenceError, match="fenced block"):
        load_examples(tmp_path)


def test_loader_rejects_a_kind_that_doesnt_match_the_file(tmp_path):
    (tmp_path / "standards.md").write_text("<!-- example: model-evals/best -->\n```json\n{}\n```\n")
    with pytest.raises(ReferenceError, match="file name"):
        load_examples(tmp_path)


# -- Acceptance Criteria -----------------------------------------------------------------


def test_weak_criteria_fail_for_the_documented_reasons():
    s = score_criteria(body("acceptance-criteria/weak"))
    gates = " ".join(s.gates)
    assert "between 2 and 8" in gates and '"critical"' in gates and "AC9" in gates
    warned = " ".join(s.warnings)
    for ac in ("AC1", "AC2", "AC4", "AC5"):  # the untestable wording the file names
        assert ac in warned
    assert any("title" in w for w in s.warnings)
    assert s.metrics["criteria"] == 9


def test_best_criteria_are_shorter_than_weak():
    best = score_criteria(body("acceptance-criteria/best")).metrics["chars"]
    weak = score_criteria(body("acceptance-criteria/weak")).metrics["chars"]
    assert best < weak


def _criteria(*crits: tuple[str, str]) -> str:
    """A valid intake answer with the given (verification, text) criteria."""
    items = [{"id": f"AC{i}", "text": text, "severity": "critical" if i == 1 else "major",
              "verification": ver, "check": "tests_pass" if ver == "deterministic" else None,
              "required_evidence": "test passes"} for i, (ver, text) in enumerate(crits, 1)]
    return json.dumps({"route": "code", "answer": "", "task_title": "Add f",
                       "task_description": "Add f.", "acceptance_criteria": items,
                       "constraints": [], "unsupported_reason": ""})


# Real criteria from Ezra's first coding tasks (2026-11-20/21): all passed Guardian, so the
# checklist should have nothing to say about their wording.
REAL_CRITERIA = [
    'sentence_count("Hello there") with no terminating punctuation returns 0.',
    'char_count("a\\tb\\nc\\r\\nd") returns 4 (tabs, newlines and carriage returns are not '
    'counted).',
    'Ties in count are broken alphabetically (ascending): top_words("pear apple fig", 3) '
    'returns [("apple", 1), ("fig", 1), ("pear", 1)].',
    'longest_word of whitespace-only text such as "   \\t\\n" returns "".',
    'unique_words can be imported from the textkit package via `from textkit import '
    'unique_words` and is the same function as textkit.stats.unique_words.',
]


@pytest.mark.parametrize("text", REAL_CRITERIA)
def test_real_concrete_criteria_get_no_wording_warning(text):
    s = score_criteria(_criteria(("test", text)))
    assert not [w for w in s.warnings if "AC1" in w], s.warnings


@pytest.mark.parametrize("text", [
    "word_count() handles edge cases",          # a call, but no result and vague
    "The function returns the right answer.",   # a result, but nothing to call
    "Supports Unicode text including emoji.",
])
def test_criteria_without_input_and_result_are_not_concrete(text):
    s = score_criteria(_criteria(("test", text)))
    assert any("AC1" in w and "expected result" in w for w in s.warnings), s.warnings


def test_vague_words_inside_quotes_or_code_dont_count():
    s = score_criteria(_criteria(("test", 'is_fast("fast") returns True and `quickly()` '
                                          'returns 1.')))
    assert not [w for w in s.warnings if "vague" in w]
    s = score_criteria(_criteria(("test", "parse(x) returns the result quickly.")))
    assert any("vague" in w and "quickly" in w for w in s.warnings)


def test_free_deterministic_checks_dont_count_toward_the_criteria_range():
    six_tests = [("test", f"f({i}) returns {i}.") for i in range(6)]
    s = score_criteria(_criteria(*six_tests, ("deterministic", "The test suite passes.")))
    assert s.metrics == {**s.metrics, "criteria": 7, "model_criteria": 6}
    assert not [w for w in s.warnings if "criteria besides" in w]
    s = score_criteria(_criteria(*six_tests, ("test", "f(9) returns 9."),
                                 ("deterministic", "The test suite passes.")))
    assert any("7 criteria besides free checks" in w for w in s.warnings)


def test_criteria_that_arent_json_fail_a_gate():
    assert score_criteria("route: code").gates == ["not valid JSON (Expecting value)"]


def test_non_code_routes_get_no_criteria_warnings():
    s = score_criteria(json.dumps({
        "route": "direct", "answer": "4", "task_title": "", "task_description": "",
        "acceptance_criteria": [], "constraints": [], "unsupported_reason": ""}))
    assert s.clean


# -- Standards ---------------------------------------------------------------------------


def test_required_standard_fields_come_from_the_template():
    fields, sections = template_fields()
    assert "guardian_validation" in fields and "required_evidence" in fields
    assert sections[:4] == ["Requirement", "Rationale", "Passing conditions",
                            "Failure conditions"]


def test_weak_standard_fails_for_the_documented_reasons():
    s = score_standard(body("standards/weak"))
    gates = " ".join(s.gates)
    assert "verification" in gates and "required_evidence" in gates
    assert "D-006" in gates
    assert "circular" in gates
    warned = " ".join(s.warnings)
    assert "in detail" in warned and "user_confirmed" in warned


def _best_standard(**changes: str) -> str:
    text = body("standards/best")
    for old, new in changes.items():
        assert old in text
        text = text.replace(old, new)
    return text


def test_standard_scope_must_match_its_id():
    s = score_standard(_best_standard(**{"scope: global": "scope: department"}))
    assert any("id letter G" in g for g in s.gates)


def test_standard_with_unknown_department_fails():
    s = score_standard(_best_standard(**{"applies_to: [all]": "applies_to: [marketing]"}))
    assert any("applies_to" in g for g in s.gates)


def test_activating_a_standard_needs_guardian_validation():
    active = _best_standard(**{"status: draft": "status: active"})
    assert any("D-006" in g for g in score_standard(active).gates)
    validated = active.replace("guardian_validation: null", "guardian_validation: gv_123")
    assert score_standard(validated).clean


def test_standard_without_frontmatter_fails():
    assert score_standard("## Requirement\nDo it.").gates


# -- Quality Rubric: answers and Guardian's review ------------------------------------------


def test_weak_answer_warnings_name_the_padding():
    s = score("answer", body("quality-rubric/weak"))
    warned = " ".join(s.warnings)
    assert "great question" in warned and "i hope this helps" in warned
    assert "headings" in warned
    assert s.metrics["words"] > 3 * score("answer", body("quality-rubric/best")).metrics["words"]


def test_preamble_is_only_looked_for_in_the_first_sentence():
    assert not score("answer", "Run it twice. Make sure, of course!, to save first.").warnings
    assert any("preamble" in w for w in score("answer", "Sure! Run it twice.").warnings)


def test_new_sign_offs_are_caught():
    s = score("answer", "Run `make`.\n\nGood luck with the build.")
    assert any("good luck" in w for w in s.warnings)


def test_code_blocks_dont_count_toward_the_heading_threshold():
    code = "```python\n" + "x = 1\n" * 400 + "```\n"
    s = score("answer", f"## Fix\n\nUse this:\n\n{code}")
    assert s.metrics["prose_words"] < 300 < s.metrics["words"]
    assert any("headings" in w for w in s.warnings)
    long_prose = " ".join(["word"] * 320)
    assert not score("answer", f"## Part one\n\n{long_prose}").warnings


def _review(**changes) -> str:
    data = json.loads(body("quality-rubric/best-review"))
    data.update(changes)
    return json.dumps(data)


def test_review_grade_must_match_the_scores():
    s = score_review(_review(grade="pass"))
    assert any("rubric.grade" in g for g in s.gates)


def test_review_needs_a_reason_for_every_score():
    data = json.loads(body("quality-rubric/best-review"))
    data["scores"]["A_accuracy"] = [5, " "]
    assert any("GRD-2" in g for g in score_review(json.dumps(data)).gates)


def test_review_must_use_the_current_rubric_version():
    assert any("rubric_version" in g for g in score_review(_review(rubric_version="0")).gates)


def test_review_with_a_missing_category_fails():
    data = json.loads(body("quality-rubric/best-review"))
    del data["scores"]["G_presentation"]
    assert any("rubric v1" in g for g in score_review(json.dumps(data)).gates)


def test_review_rejects_unknown_agent_checks():
    assert any("XYZ-1" in g for g in score_review(_review(agent_checks={"XYZ-1": True})).gates)


def test_review_with_a_critical_failure_must_grade_fail():
    s = score_review(_review(critical_failures=["fabrication"]))
    assert any("'fail'" in g for g in s.gates)
    assert score_review(_review(critical_failures=["fabrication"], grade="fail")).passed


# -- Model Evals -------------------------------------------------------------------------


def _eval(mutate) -> str:
    data = json.loads(body("model-evals/best"))
    mutate(data)
    return json.dumps(data)


def test_eval_costs_are_recomputed_from_pricing():
    def wrong_cost(d):
        d["cases"][0]["cost_usd"] = 0.001
    gates = score_eval(_eval(wrong_cost)).gates
    assert any("BLD-CG-01" in g and "0.01558" in g for g in gates)
    assert any("total_cost_usd" in g for g in gates)


def test_eval_summary_must_match_the_cases():
    def wrong_rate(d):
        d["summary"]["pass_rate"] = 1.0
    assert any("3/4" in g for g in score_eval(_eval(wrong_rate)).gates)


def test_eval_model_must_be_an_exact_priced_id():
    def short_name(d):
        d["model"] = "sonnet"
    assert any("pricing.yaml" in g for g in score_eval(_eval(short_name)).gates)


def test_eval_cant_qualify_on_one_run():
    def qualify(d):
        d["status"] = "qualified"
    assert any("D-012" in g for g in score_eval(_eval(qualify)).gates)


def test_eval_case_failures_must_match_its_gate_result():
    def inconsistent(d):
        d["cases"][2]["failures"] = []
    gates = score_eval(_eval(inconsistent)).gates
    assert any("BLD-CG-03" in g for g in gates) and any("failure_types" in g for g in gates)


def test_weak_eval_fails_on_schema():
    assert any(g.startswith("schema:") for g in score_eval(body("model-evals/weak")).gates)


# -- wiring: intake logs its benchmark, the CLI scores files ------------------------------


def test_intake_logs_a_benchmark_score_without_an_extra_call(tmp_path, git_repo):
    store = Store(tmp_path / "ezra.db")
    try:
        client = FakeClient([decision("code")])
        gw = Gateway(store=store, routing=load_routing(), limits=load_limits(),
                     pricing=load_pricing(), client=client)
        result = run_intake(gw, "Add sentence_count", project=git_repo, limits=load_limits())
        events = store.events_for_task(result.request_id)
    finally:
        store.close()
    assert len(result.invocations) == 1
    bench = [e for e in events if e["kind"] == "intake_benchmark"]
    assert len(bench) == 1 and bench[0]["benchmark_version"] == "2"
    assert bench[0]["scored"] == "acceptance-criteria"
    assert bench[0]["metrics"]["criteria"] == 3
    # The test fixture's criteria say "behavior 1": the benchmark flags them as untestable.
    assert any("AC1" in w for w in bench[0]["warnings"])


def test_intake_scores_direct_answers_too(tmp_path, git_repo):
    store = Store(tmp_path / "ezra.db")
    try:
        gw = Gateway(store=store, routing=load_routing(), limits=load_limits(),
                     pricing=load_pricing(), client=FakeClient([decision("direct")]))
        result = run_intake(gw, "what's 2+2", project=git_repo, limits=load_limits())
        events = store.events_for_task(result.request_id)
    finally:
        store.close()
    bench = [e for e in events if e["kind"] == "intake_benchmark"]
    assert len(result.invocations) == 1  # still no extra call
    assert len(bench) == 1 and bench[0]["scored"] == "quality-rubric"
    assert "words" in bench[0]["metrics"]


def test_trace_shows_the_intake_benchmark():
    from ezra.trace import _event_detail
    step, text = _event_detail("intake_benchmark", {
        "benchmark_version": "2", "scored": "acceptance-criteria",
        "warnings": ["AC2: vague wording ['robust']"]})
    assert step == "intake" and "1 warning(s)" in text and "robust" in text
    assert "answer clean" in _event_detail("intake_benchmark", {
        "benchmark_version": "2", "scored": "quality-rubric", "warnings": []})[1]


def test_cli_checks_the_reference_files(capsys):
    assert cli.main(["bench", "references"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert out.count("ok  ") == len(EXAMPLES) and "FAIL" not in out


def test_cli_scores_a_file(tmp_path, capsys):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(body("model-evals/best"))
    bad.write_text(body("model-evals/weak"))
    assert cli.main(["bench", "eval", str(good)]) == cli.EXIT_OK
    assert "PASS" in capsys.readouterr().out
    assert cli.main(["bench", "eval", str(bad)]) == cli.EXIT_ERROR
    assert "gate" in capsys.readouterr().out
