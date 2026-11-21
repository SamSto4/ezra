# Reference output: Acceptance Criteria

**Produced by:** Ezra intake (`ezra.intake`, routed to Sonnet 5.5) for every `code` request.
**Read by:** Code Joe (plans from it), Tester (writes one test per test-verified criterion),
Guardian (judges each criterion met / unmet / cannot_verify).
**Governed by:** D-001, D-002, `intake.py` (schema + `problems_with()`), `contracts.AcceptanceCriterion`.

## What "best" means here

The best criteria set is the **smallest set that pins down "done"** so that a stranger could
write the tests without seeing the code, and Guardian can rule on each item without
interpretation. Every extra criterion is a test to write, a check to run and a place to fail,
so it costs tokens three times over. Every vague criterion turns into `cannot_verify`, which
counts as unmet (D-002), which costs a correction cycle.

| Property | Best output | Why it saves tokens |
|---|---|---|
| Count | 3–6 criteria, one behaviour each | Fewer tests and fewer review items; nothing to argue about |
| Wording | Names the function, an input and the exact expected output | Tester writes the test from the text alone; no adjudication loop |
| Severity | Exactly the core behaviour is `critical`; important edges `major`; polish `minor` | Guardian only blocks on what matters |
| Verification | `test` for behaviour, `deterministic` + `check` for suite/lint, `inspection` only when no test can check it | Deterministic checks cost zero model calls (D-007) |
| Scope | Only what the user asked or clearly implied; assumptions go in `constraints` | No invented features to build, test and review |
| Shape | Passes `problems_with()` first time | A repair is a second paid call |

## Same request, two outputs

Request: *"Add a word_count function to textkit that counts the words in a string."*

### Weak (fails validation, then costs a repair call)

<!-- example: acceptance-criteria/weak -->
```json
{
  "route": "code",
  "answer": "",
  "task_title": "Implement a robust, well-documented word counting feature for textkit",
  "task_description": "The user would like a new function added to the textkit package which will count the number of words that appear in a given string of text. This function should be robust, handle a wide range of possible inputs gracefully, follow best practices, and be well documented so that future maintainers can understand it.",
  "acceptance_criteria": [
    {"id": "AC1", "text": "The word_count function works correctly.", "severity": "major", "verification": "test", "check": null, "required_evidence": "Tests pass."},
    {"id": "AC2", "text": "Edge cases are handled gracefully.", "severity": "major", "verification": "test", "check": null, "required_evidence": "Edge case tests."},
    {"id": "AC3", "text": "Supports Unicode text including emoji and right-to-left scripts.", "severity": "major", "verification": "test", "check": null, "required_evidence": "Unicode tests pass."},
    {"id": "AC4", "text": "Handles very large inputs efficiently.", "severity": "major", "verification": "inspection", "check": null, "required_evidence": "Reviewer confirms efficiency."},
    {"id": "AC5", "text": "Code is clean and follows best practices.", "severity": "major", "verification": "inspection", "check": null, "required_evidence": "Reviewer approval."},
    {"id": "AC6", "text": "Function has a comprehensive docstring with examples.", "severity": "minor", "verification": "inspection", "check": null, "required_evidence": "Docstring present."},
    {"id": "AC7", "text": "Type hints are used throughout.", "severity": "minor", "verification": "inspection", "check": null, "required_evidence": "Type hints present."},
    {"id": "AC8", "text": "A CLI command for word counting is added.", "severity": "minor", "verification": "test", "check": null, "required_evidence": "CLI test passes."},
    {"id": "AC9", "text": "All tests pass.", "severity": "major", "verification": "deterministic", "check": null, "required_evidence": "pytest output."}
  ],
  "constraints": [],
  "unsupported_reason": ""
}
```

What's wrong, in Guardian's terms:
- **Fails `problems_with()` three ways:** 9 criteria (max 8), no `critical` criterion, and AC9 is
  `deterministic` with no `check`. The repair is a second full call.
- **Untestable wording:** AC1, AC2, AC4 and AC5 give Tester nothing concrete, so Guardian can
  only answer `cannot_verify`, which counts as unmet.
- **Invented scope:** Unicode/RTL (AC3), performance (AC4) and a CLI (AC8) were never asked for.
  Each one is work to build, test and review.
- **Padding:** the long title and description add tokens that every later step re-reads.

### Best (passes first time)

<!-- example: acceptance-criteria/best -->
```json
{
  "route": "code",
  "answer": "",
  "task_title": "Add word_count to textkit",
  "task_description": "Add word_count(text: str) -> int to textkit, counting whitespace-separated words.",
  "acceptance_criteria": [
    {"id": "AC1", "text": "word_count(\"the quick  brown fox\") returns 4 (runs of whitespace count as one separator).", "severity": "critical", "verification": "test", "check": null, "required_evidence": "Acceptance test for AC1 passes."},
    {"id": "AC2", "text": "word_count(\"\") and word_count(\"   \\n\\t\") both return 0.", "severity": "major", "verification": "test", "check": null, "required_evidence": "Acceptance test for AC2 passes."},
    {"id": "AC3", "text": "word_count(\"hello, world!\") returns 2: punctuation stays attached to its word.", "severity": "major", "verification": "test", "check": null, "required_evidence": "Acceptance test for AC3 passes."},
    {"id": "AC4", "text": "word_count is importable as `from textkit import word_count`.", "severity": "major", "verification": "test", "check": null, "required_evidence": "Acceptance test for AC4 passes."},
    {"id": "AC5", "text": "The existing test suite still passes.", "severity": "major", "verification": "deterministic", "check": "tests_pass", "required_evidence": "pytest exit code 0."}
  ],
  "constraints": ["No new dependencies."],
  "unsupported_reason": ""
}
```

Why it's best: five criteria, each one behaviour with an exact input and output. The one
judgement call the user didn't specify (punctuation) is made explicit in AC3 so Guardian
can hold Code Joe to it. One `critical`, and the suite check is free (deterministic).

## Checklist for intake

- [ ] 3–6 criteria; ids AC1… in order; at least one `critical`.
- [ ] Every `test` criterion names a call and its exact result.
- [ ] `check` is set on, and only on, `deterministic` criteria.
- [ ] Nothing the user didn't ask for; assumptions are stated, not built.
- [ ] Title under 60 characters, description 1–3 sentences.

## Sources

See [model-evals.md § Sources](model-evals.md#sources) for the shared evidence behind
"shortest output that fully meets the requirements".
