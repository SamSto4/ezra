# Reference output: Quality Rubric

**Produced by:** any agent's text output is *graded*; Guardian *produces* the grade.
**Used at:** Tier 3 reviews (D-007) and offline scoring for Model Evals. Phase 1 doesn't run it live.
**Governed by:** D-002, D-003, D-014, [config/rubric.yaml](../../config/rubric.yaml) v1,
`guardian/rubric.py`.

This file shows two reference outputs: **an answer that grades `excellent`**, and **the review
Guardian should write about it**.

## What "best" means here

The rubric rewards outputs that *accomplish the purpose* (A, B, C are the core gates). It
never rewards length: the spec says length and presentation "must not be mistaken for
usefulness", and Clarity explicitly penalises repetition. So the best answer is **the shortest
one that is correct, does what was asked, and can be used as is.**

| Category (weight) | What a 5 looks like | What wastes tokens and lowers the score |
|---|---|---|
| A Accuracy (20) | Every claim true; the likely cause is named, not a list of maybes | Generic cause lists that include wrong advice |
| B Instructions (20) | Answers "why" **and** "how to fix", nothing else | Restating the question; unrequested extras |
| C Task achieved (20) | User can fix it in one step and confirm the fix | Options without a recommendation |
| D Context (10) | Uses the details given (file name, fixture name) | Ignoring them and answering generically |
| E Reasoning (20) | Explains the mechanism that causes the error | Shotgun troubleshooting |
| F Clarity (5) | Short, ordered, no repetition | Preamble, recap, sign-off |
| G Presentation (5) | Code block for the fix, command to verify | Headings and bullets for a 3-step answer |

## Reference answer: same question, two outputs

Question: *"My pytest run fails with `fixture 'tmp_repo' not found`. The fixture is defined in
tests/helpers.py. Why, and how do I fix it?"*

### Weak answer (grades `conditional`: A and C at 3)

<!-- example: quality-rubric/weak -->
```markdown
Great question! Fixture errors in pytest can be frustrating, but don't worry, they're usually
easy to fix. Let's walk through this step by step.

## Understanding the Error

The error `fixture 'tmp_repo' not found` means that pytest was unable to find a fixture named
`tmp_repo` when it tried to run your test. Fixtures are a powerful feature of pytest that let
you set up reusable test resources.

## Possible Causes

There are several reasons this might happen:

1. **Typo in the fixture name**: double-check that the name in your test matches exactly.
2. **The fixture isn't registered**: pytest needs to know about your fixture.
3. **Scope issues**: the fixture might be defined with the wrong scope.
4. **Outdated pytest version**: try upgrading with `pip install --upgrade pytest`.
5. **Virtual environment problems**: make sure you're using the right environment.
6. **Cache issues**: try deleting the `.pytest_cache` folder.
7. **File location**: make sure `helpers.py` is in the same folder as your tests. pytest will
   pick up fixtures from any file in that folder.

## Recommended Steps

I'd recommend going through each of these causes one by one until you find the issue. Start
with the simplest ones, like checking for typos, and work your way up.

## Conclusion

Fixture errors are common and usually have a simple fix. I hope this helps! Let me know if you
have any other questions or if the problem persists.
```

How Guardian scores it (rubric v1):
- **A Accuracy 3:** cause 7 is false (pytest does not load fixtures from arbitrary modules) and
  causes 3–6 can't produce this error.
- **C Task achieved 3:** no fix the user can apply; "go through each cause" is not a fix.
- **E Reasoning 2, F Clarity 2:** no mechanism; preamble, recap and sign-off are repetition.
- The real answer is hidden at item 2 without saying *how* to register the fixture.

### Best answer (grades `excellent`)

<!-- example: quality-rubric/best -->
```markdown
pytest only discovers fixtures in `conftest.py` files, the test module itself, and loaded
plugins. `tests/helpers.py` is a plain module, so `tmp_repo` is never registered.

Fix: move the fixture into `tests/conftest.py`:

    # tests/conftest.py
    import pytest

    @pytest.fixture
    def tmp_repo(tmp_path):
        ...

Check: `pytest --fixtures tests | grep tmp_repo` should now list it.
```

Why it's best: the first sentence is the mechanism (E), the second applies it to the user's
file (D), then one fix and one way to confirm it (C). Every sentence is load-bearing, and it's
about a third the length of the weak answer.

## Reference review: Guardian's grade of the best answer

Guardian reviews **evidence, not transcripts** (D-007), returns scores **with a reason each**,
and stays short because its output is re-read by Ezra and stored for Model Evals.

### Weak review

<!-- example: quality-rubric/weak-review -->
```markdown
This is an excellent and very comprehensive response that demonstrates a strong understanding
of pytest and its fixture system. The answer is clear, well organized and professional, and it
directly addresses the user's question in a helpful way. The explanation of fixture discovery
is accurate and the suggested fix is appropriate. The formatting is clean and the response is
concise. Overall, I would rate this response very highly across all categories.

Scores: Accuracy 5, Instruction adherence 5, Task achievement 5, Context 5, Reasoning 5,
Clarity 5, Presentation 5. No issues found. Verdict: PASS.
```

What's wrong: no evidence for any score (breaks agent check GRD-2), no rubric version, no
critical-failure check, no agent checks; praise adjectives cost tokens and carry no
information. The same text could have been written without reading the answer, which is
exactly how false approvals (GRD-1) happen.

### Best review

<!-- example: quality-rubric/best-review -->
```json
{
  "rubric_version": "1",
  "scores": {
    "A_accuracy": [5, "Discovery rule is correct; conftest.py fix and --fixtures check both valid."],
    "B_instruction_adherence": [5, "Answers why and how to fix; nothing else."],
    "C_task_achievement": [5, "One applicable fix plus a command that confirms it."],
    "D_context_awareness": [5, "Uses the user's file and fixture names."],
    "E_reasoning": [5, "States the mechanism before the fix."],
    "F_clarity": [5, "Three short parts, no repetition."],
    "G_presentation": [4, "Indented code instead of a fenced block; minor."]
  },
  "critical_failures": [],
  "agent_checks": {"EZR-1": true, "EZR-2": true, "EZR-3": true},
  "grade": "excellent",
  "notes": ["G: prefer fenced code blocks."]
}
```

Why it's best: every score cites what was checked, the grade is reproducible by
`rubric.grade()` from the scores, the minor note is actionable, and it's machine-readable so
nothing has to be re-parsed.

## Checklist

For any graded output:
- [ ] Lead with the answer; first sentence carries the main point.
- [ ] Answer exactly what was asked; say what you assumed.
- [ ] One recommendation, not a menu, unless the user asked for options.
- [ ] No preamble, recap or sign-off. Formatting only where it helps use the output.

For Guardian's review:
- [ ] One reason per score, citing the output.
- [ ] Critical failures checked explicitly, even when the list is empty.
- [ ] Structured output; no adjectives without evidence.

## Sources

See [model-evals.md § Sources](model-evals.md#sources) for the shared evidence behind
"shortest output that fully meets the requirements".
