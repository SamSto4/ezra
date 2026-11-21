"""Progressive learning (D-012): lessons are judged, distilled, validated, stored, retrieved
and rated. Scripted model, no network; the end-to-end tests use real git and real pytest."""

import json
import subprocess
from datetime import timedelta

import pytest
from fakes import FakeClient, ScriptedClient, message, tool_turn

from ezra import core
from ezra.code_joe.agents import BUILD_SYSTEM, PLAN_SYSTEM, TEST_SYSTEM
from ezra.config import LearningConfig, load_learning, load_limits, load_routing
from ezra.contracts import (
    AcceptanceCriterion,
    Budget,
    Department,
    DeterministicCheck,
    Lesson,
    LessonKind,
    LessonStatus,
    Severity,
    TaskEnvelope,
    TaskStatus,
    Verification,
    utcnow,
)
from ezra.gateway import Gateway
from ezra.guardian.tier2 import SYSTEM as GUARDIAN_SYSTEM
from ezra.learner.curator import CurationReport, apply_proposals, apply_ratings, similarity
from ezra.learner.reflector import SYSTEM as REFLECT_SYSTEM
from ezra.learner.reflector import ProposedLesson
from ezra.learner.retrieval import HEADER, LessonProvider, render, select_lessons
from ezra.learner.validator import task_literals, validate
from ezra.pricing import load_pricing
from ezra.store import Store

ON = LearningConfig(memory="lessons")
OPS = ON.inject_into


def lesson(op="builder.implement", text="Handle empty input explicitly before looping.",
           trigger="a criterion mentions empty or missing input", project=None, **kw):
    return Lesson(operation=op, kind=LessonKind.PITFALL, trigger=trigger, text=text,
                  project=project, **kw)


def proposal(text="Implement the general rule for every input; never map known inputs to "
                  "expected outputs.", trigger="the criteria give example inputs and outputs",
             op="builder.implement", merge_with=""):
    return ProposedLesson(operation=op, kind="pitfall", trigger=trigger, text=text,
                          merge_with=merge_with)


def task_env(**kw):
    return TaskEnvelope(
        target_department=Department.CODE_JOE, budget=Budget(task_limit_usd=2.0,
                                                             daily_limit_usd=10.0),
        description=kw.pop("description", 'Add slugify(text) so "Hello World" becomes '
                                          '"hello-world" and 2048 stays'),
        acceptance_criteria=[AcceptanceCriterion(
            id="AC1", text='slugify("Hello World") returns "hello-world"',
            severity=Severity.CRITICAL, verification=Verification.TEST)], **kw)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "ezra.db")
    yield s
    s.close()


# -- store -------------------------------------------------------------------------------


def test_lessons_are_versioned_and_uses_counted_once(store):
    lsn = lesson()
    store.save_lesson(lsn, "added", "task_a", reason="first")
    store.save_lesson(lsn.model_copy(update={"version": 2, "helpful": 1}), "rated", "task_b")
    assert store.get_lesson(lsn.lesson_id).helpful == 1
    assert [h["action"] for h in store.lesson_history(lsn.lesson_id)] == ["added", "rated"]
    assert store.lessons(LessonStatus.ACTIVE, "builder.implement")[0].version == 2
    assert store.lessons(LessonStatus.ACTIVE, "tester.write_tests") == []
    for _ in range(3):  # every turn of an agent loop records the same use
        store.record_lesson_use("task_c", lsn.lesson_id, "builder.implement")
    assert store.lessons_used_by_task("task_c") == [lsn.lesson_id]


# -- retrieval ---------------------------------------------------------------------------


def test_retrieval_ranks_filters_caps_and_renders_in_a_stable_order(store):
    now = utcnow()
    best = lesson(text="Best lesson, proven helpful several times over.", helpful=3)
    mid = lesson(text="Middle lesson, reinforced by two tasks.", evidence=["t1", "t2"])
    low = lesson(text="Low lesson that once caused trouble here.", harmful=1)
    other_project = lesson(text="Only for another project entirely.", project="elsewhere",
                           helpful=9)
    retired = lesson(text="Retired lessons are never retrieved.", helpful=9,
                     status=LessonStatus.RETIRED)
    other_op = lesson(op="tester.write_tests", text="For Tester only, not for Builder.")
    for i, lsn in enumerate((best, mid, low, other_project, retired, other_op)):
        store.save_lesson(lsn.model_copy(update={"updated_at": now - timedelta(minutes=i)}),
                          "added")
    picked = select_lessons(store, "builder.implement", "playground", token_cap=10_000)
    assert {lsn.lesson_id for lsn in picked} == {best.lesson_id, mid.lesson_id, low.lesson_id}
    assert [lsn.lesson_id for lsn in picked] == sorted(lsn.lesson_id for lsn in picked)
    # A tight cap keeps the highest-ranked lesson.
    tight = select_lessons(store, "builder.implement", "playground", token_cap=90)
    assert [lsn.lesson_id for lsn in tight] == [best.lesson_id]
    assert render(tight).startswith(HEADER) and best.text in render(tight)
    assert render([]) == ""


def test_provider_chooses_once_per_task_and_logs_the_use(store, tmp_path):
    env = task_env(project_ref=str(tmp_path / "playground"))
    store.save_task(env)
    lsn = lesson()
    store.save_lesson(lsn, "added")
    provider = LessonProvider(store, ON)
    text, refs = provider.for_call(env.task_id, "builder.implement")
    store.save_lesson(lesson(text="Added mid-task; must not change this task's block."),
                      "added")
    assert provider.for_call(env.task_id, "builder.implement") == (text, refs)
    assert refs == [lsn.lesson_id] and lsn.text in text
    assert provider.for_call(env.task_id, "guardian.tier2") == ("", [])  # judge stays clean
    assert store.lessons_used_by_task(env.task_id) == [lsn.lesson_id]
    assert [e["kind"] for e in store.events_for_task(env.task_id)] == ["lessons_injected"]


# -- validation ----------------------------------------------------------------------------


def test_validator_accepts_a_general_lesson():
    assert validate(proposal(), task_env(), OPS).ok


@pytest.mark.parametrize("text,trigger,op,reason", [
    ("Make AC1 pass by lowercasing before replacing spaces.", "slug tasks",
     "builder.implement", "specific id"),
    ("Put the edge cases in tests/acceptance/test_slug.py first.", "slug tasks",
     "tester.write_tests", "acceptance test files"),
    ("Remember that the expected output is hello-world for this kind of input.",
     "slug tasks", "builder.implement", "hello-world"),
    ("Numbers such as 2048 must pass through unchanged by the transformation.",
     "number inputs", "builder.implement", "2048"),
    ("Follow best practices and be careful.", "always", "builder.implement", "vague"),
    ("Too short.", "always", "builder.implement", "characters"),
    ("Check every criterion against the diff before you approve the change.", "reviews",
     "guardian.tier2", "doesn't receive lessons"),
])
def test_validator_rejects_leakage_vagueness_and_wrong_targets(text, trigger, op, reason):
    check = validate(ProposedLesson(operation="builder.implement", kind="check",
                                    trigger=trigger, text=text, merge_with="")
                     .model_copy(update={"operation": op}), task_env(), OPS)
    assert not check.ok and reason in check.reason


def test_task_literals_ignore_tiny_strings_but_keep_numbers():
    env = task_env(description='Split on "," or "ab" and cap at 10; don\'t trim the user\'s text')
    lits = task_literals(env)
    assert lits == {"10", "hello world", "hello-world"}


# -- curation ------------------------------------------------------------------------------


def test_curator_adds_merges_duplicates_and_respects_the_cap(store):
    report = CurationReport()
    cfg = LearningConfig(memory="lessons", max_active_per_operation=2)
    apply_proposals(store, [proposal()], "task_1", "playground", cfg, report)
    first = report.added[0]
    # Same idea, slightly reworded: merged into the first lesson, text unchanged.
    reworded = proposal(text="Implement the general rule for every input and never map "
                             "known inputs to expected outputs.")
    apply_proposals(store, [reworded], "task_2", "playground", cfg, report)
    merged = store.get_lesson(first)
    assert report.merged == [first] and merged.evidence == ["task_1", "task_2"]
    assert merged.version == 2 and merged.text == proposal().text
    # merge_with names an existing lesson explicitly.
    apply_proposals(store, [proposal(text="Something phrased very differently but the same.",
                                     merge_with=first)], "task_3", "playground", cfg, report)
    assert store.get_lesson(first).evidence == ["task_1", "task_2", "task_3"]
    # Two genuinely new lessons: the cap of 2 retires the weakest older one.
    apply_proposals(store, [proposal(text="Read the existing module before writing so the "
                                          "public exports stay intact.", trigger="editing "
                                          "a package"),
                            proposal(text="Return the documented type exactly; tests compare "
                                          "with equality, not truthiness.", trigger="a "
                                          "signature names a return type")],
                    "task_4", "playground", cfg, report)
    assert len(store.lessons(LessonStatus.ACTIVE, "builder.implement")) == 2
    assert report.retired and first not in report.retired  # reinforced 3x, so it survives


def test_ratings_count_uses_and_retire_harmful_lessons(store):
    lsn = lesson()
    store.save_lesson(lsn, "added")
    report = CurationReport()
    apply_ratings(store, [lsn.lesson_id], {lsn.lesson_id: "harmful"}, "t1", ON, report)
    assert store.get_lesson(lsn.lesson_id).status is LessonStatus.ACTIVE  # one vote isn't enough
    apply_ratings(store, [lsn.lesson_id], {lsn.lesson_id: "harmful"}, "t2", ON, report)
    after = store.get_lesson(lsn.lesson_id)
    assert (after.uses, after.harmful, after.status) == (2, 2, LessonStatus.RETIRED)
    assert [h["action"] for h in store.lesson_history(lsn.lesson_id)] == \
        ["added", "rated", "rated", "retired"]


def test_similarity_ignores_stop_words():
    assert similarity("the cat and the hat", "cat hat") == 1.0
    assert similarity("", "x") == 0.0


# -- gateway -------------------------------------------------------------------------------


def test_gateway_sends_context_as_a_second_cached_block_and_logs_its_ids(store):
    client = FakeClient()
    gw = Gateway(store=store, routing=load_routing(), limits=load_limits(),
                 pricing=load_pricing(), client=client)
    resp = gw.call(operation="builder.implement", department=Department.BUILDER,
                   system="static", messages=[{"role": "user", "content": "hi"}],
                   max_tokens=100, system_context="## Lessons\n- one",
                   context_refs=["les_1"])
    sent = client.messages.stream_calls[0]["system"]
    counted = client.messages.count_calls[0]["system"]
    assert [b["text"] for b in sent] == ["static", "## Lessons\n- one"]
    assert all(b["cache_control"] == {"type": "ephemeral"} for b in sent)
    assert counted == sent  # the budget check counts the lessons too
    assert resp.invocation.context_refs == ["les_1"]
    # M6 attribution records the lesson block as a labelled context piece.
    assert [c.label for c in resp.invocation.context] == ["lessons"]


# -- end to end ------------------------------------------------------------------------------

GOOD = "def double(x: int) -> int:\n    return x * 2\n"
HARDCODED = "def double(x: int) -> int:\n    return {2: 4}.get(x, 0)\n"
TESTS = "from calc import double\n\n\ndef test_ac1_doubles_two():\n    assert double(2) == 4\n"
PLAN_JSON = json.dumps({
    "summary": "Add calc.py with double().", "steps": ["Create calc.py"],
    "interface": [{"path": "calc.py", "symbol": "double", "signature": "double(x: int) -> int",
                   "description": "Returns x times two."}],
    "test_file": "tests/acceptance/test_calc.py"})
LESSON_TEXT = ("Implement the general rule for every input; never map known example inputs "
               "to their expected outputs.")


def guardian(findings=(), corrections=()):
    return message(json.dumps({
        "criteria": [],
        "findings": [{"code": c, "severity": s, "message": m, "auto_fixable": True}
                     for c, s, m in findings],
        "required_corrections": list(corrections), "summary": "ok"}), model="claude-opus-5-5")


def reflection(lessons=(), ratings=()):
    return message(json.dumps({"lessons": list(lessons), "ratings": list(ratings)}))


def writes(path, content):
    return tool_turn(("write_file", {"path": path, "content": content}))


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "proj"
    (repo / "tests" / "acceptance").mkdir(parents=True)
    (repo / "tests" / "acceptance" / ".gitkeep").write_text("")
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["."]\ntestpaths = ["tests"]\n')
    for cmd in (["init", "-q"], ["add", "-A"],
                ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    return repo


def new_task(store, project, task_limit=2.0):
    env = TaskEnvelope(
        target_department=Department.CODE_JOE, description="Add double(x) to calc.py",
        project_ref=str(project),
        acceptance_criteria=[
            AcceptanceCriterion(id="AC1", text="double(2) returns 4",
                                severity=Severity.CRITICAL, verification=Verification.TEST),
            AcceptanceCriterion(id="AC2", text="existing tests pass", severity=Severity.MAJOR,
                                verification=Verification.DETERMINISTIC,
                                check=DeterministicCheck.TESTS_PASS)],
        budget=Budget(task_limit_usd=task_limit, daily_limit_usd=10.0))
    store.save_task(env)
    return env


def run(store, tmp, scripts, task_id, memory="lessons", **client_kw):
    gw = Gateway(store=store, routing=load_routing(), limits=load_limits(),
                 pricing=load_pricing(), client=ScriptedClient(scripts, **client_kw))
    out = core.run_task(store, gw, task_id, checkpoint_path=tmp / "cp.db",
                        worktrees_dir=tmp / "wt", memory=memory, learning=ON)
    return out, gw


def systems_of(gw, static):
    return [c["system"] for c in gw.client.messages.calls if c["system"][0]["text"] == static]


REVISE_SCRIPTS = lambda: {  # noqa: E731
    PLAN_SYSTEM: [message(PLAN_JSON)],
    BUILD_SYSTEM: [writes("calc.py", HARDCODED), message("done"),
                   writes("calc.py", GOOD), message("fixed")],
    TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("done")],
    GUARDIAN_SYSTEM: [guardian([("special_cases_test_inputs", "major", "Looks up 2.")],
                               ["Implement double as x * 2."]), guardian()],
    REFLECT_SYSTEM: [reflection([{"operation": "builder.implement", "kind": "pitfall",
                                  "trigger": "the criteria give example inputs and outputs",
                                  "text": LESSON_TEXT, "merge_with": ""},
                                 {"operation": "builder.implement", "kind": "check",
                                  "trigger": "always", "text": "Make AC1 pass by returning "
                                  "the right value for the example.", "merge_with": ""}])],
}


def test_a_revise_teaches_a_lesson_that_the_next_task_uses(store, project, tmp_path):
    first = new_task(store, project)
    out, gw = run(store, tmp_path, REVISE_SCRIPTS(), first.task_id)
    assert out.outcome == "passed" and out.reviews == 2
    learned = out.learning
    assert learned.reflected and len(learned.added) == 1
    assert learned.rejected == ["builder.implement: leakage: names a specific id (AC1)"]
    les = store.get_lesson(learned.added[0])
    assert les.text == LESSON_TEXT and les.evidence == [first.task_id]
    assert les.project == "proj" and les.status is LessonStatus.ACTIVE
    # The Reflector saw Guardian's structured outcome, not a transcript.
    reflect_input = [c for c in gw.client.messages.calls
                     if c["system"][0]["text"] == REFLECT_SYSTEM][0]["messages"][0]["content"]
    assert "special_cases_test_inputs" in reflect_input and "REVISE" in reflect_input
    assert "lessons_learned" in [e["kind"] for e in store.events_for_task(first.task_id)]

    # Second task: Builder's prompt carries the lesson; Guardian's never does.
    second = new_task(store, project)
    out2, gw2 = run(store, tmp_path, {
        PLAN_SYSTEM: [message(PLAN_JSON)],
        BUILD_SYSTEM: [writes("calc.py", GOOD), message("done")],
        TEST_SYSTEM: [writes("tests/acceptance/test_calc.py", TESTS), message("done")],
        GUARDIAN_SYSTEM: [guardian()],
    }, second.task_id)
    assert out2.outcome == "passed"
    builder_systems = systems_of(gw2, BUILD_SYSTEM)
    assert builder_systems and all(len(s) == 2 and LESSON_TEXT in s[1]["text"]
                                   for s in builder_systems)
    assert all(len(s) == 1 for s in systems_of(gw2, GUARDIAN_SYSTEM))
    assert all(len(s) == 1 for s in systems_of(gw2, TEST_SYSTEM))  # no Tester lessons yet
    inv = [i for i in store.invocations_for_task(second.task_id)
           if i.operation_id == "builder.implement"]
    assert all(i.context_refs == [les.lesson_id] for i in inv)
    # A clean run: no reflection call, and the carried lesson is credited.
    assert out2.learning.skipped.startswith("clean run") and not out2.learning.reflected
    after = store.get_lesson(les.lesson_id)
    assert (after.uses, after.helpful) == (1, 1)


def test_memory_off_neither_injects_nor_learns(store, project, tmp_path):
    store.save_lesson(lesson(text=LESSON_TEXT), "added")
    env = new_task(store, project)
    scripts = REVISE_SCRIPTS()
    del scripts[REFLECT_SYSTEM]  # a reflection call would fail the test: none is scripted
    out, gw = run(store, tmp_path, scripts, env.task_id, memory="off")
    assert out.outcome == "passed" and out.learning is None
    assert all(len(s) == 1 for s in systems_of(gw, BUILD_SYSTEM))
    assert store.lessons_used_by_task(env.task_id) == []


def test_reflection_that_would_pass_the_budget_is_skipped_not_held(store, project, tmp_path):
    env = new_task(store, project)
    scripts = REVISE_SCRIPTS()
    # 2M counted input tokens: the reflection alone would cost ~$5, past the $2 cap, and
    # too big to shrink to fit (D-016). Learning must not ask for money.
    out, _ = run(store, tmp_path, scripts, env.task_id, counts={REFLECT_SYSTEM: 2_000_000})
    assert out.outcome == "passed" and out.status is TaskStatus.DONE
    assert not out.learning.reflected and "stay in budget" in out.learning.skipped
    assert store.pending_approvals() == []
    assert store.lessons() == []


def test_learning_is_once_per_finished_task(store, project, tmp_path):
    env = new_task(store, project)
    out, gw = run(store, tmp_path, REVISE_SCRIPTS(), env.task_id)
    again = core.learn(store, gw, env.task_id, ON)
    assert again.skipped == "already learned from this task"
    unfinished = new_task(store, project)
    assert "only finished tasks" in core.learn(store, gw, unfinished.task_id, ON).skipped


def test_default_config_keeps_memory_off():
    assert load_learning().memory == "off"


# -- CLI -------------------------------------------------------------------------------------


def test_cli_lists_shows_and_retires_lessons(store, tmp_path, monkeypatch, capsys):
    from ezra import cli
    monkeypatch.setattr(core, "open_store", lambda: Store(tmp_path / "ezra.db"))
    assert cli.main(["lessons"]) == cli.EXIT_OK
    assert "No lessons yet" in capsys.readouterr().out
    lsn = lesson(text=LESSON_TEXT, evidence=["task_x"])
    store.save_lesson(lsn, "added", "task_x", reason="distilled")
    assert cli.main(["lessons"]) == cli.EXIT_OK
    assert lsn.lesson_id in capsys.readouterr().out
    assert cli.main(["lessons", "show", lsn.lesson_id]) == cli.EXIT_OK
    shown = capsys.readouterr().out
    assert "v1" in shown and "added" in shown and "task_x" in shown
    assert cli.main(["lessons", "retire", lsn.lesson_id]) == cli.EXIT_OK
    assert "Retired" in capsys.readouterr().out
    assert cli.main(["lessons"]) == cli.EXIT_OK
    assert "No lessons yet" in capsys.readouterr().out
    assert cli.main(["lessons", "list", "--all"]) == cli.EXIT_OK
    assert "retired" in capsys.readouterr().out
    assert cli.main(["lessons", "retire", lsn.lesson_id]) == cli.EXIT_ERROR
