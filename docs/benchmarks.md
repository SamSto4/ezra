# Benchmarks: scoring outputs against the reference outputs

**Status:** first version, built 2026-11-21. Proposed decision below; not yet numbered, so it
can't clash with decisions added elsewhere in the meantime.

## The idea in one paragraph

`docs/reference-outputs/` shows a weak and a best example for each of the four benchmark kinds
(D-001). This turns them into something Ezra can run: a scorer per kind that checks an output
against the rules the reference file spells out, at zero model cost. The reference examples are
also the scorers' test fixtures, so if someone edits a reference file or a scorer and they stop
agreeing, the test suite fails.

```
docs/reference-outputs/*.md ──load──▶ ReferenceExample (kind, best|weak, body)
                                            │
config/benchmarks.yaml ──thresholds──▶ scorer for the kind ──▶ BenchmarkScore
contracts, intake rules, rubric.yaml,           │                 gates     (hard rules)
standards template, pricing.yaml ──rules──▶     │                 warnings  (checklist misses)
                                                ▼                 metrics   (sizes, for cost)
                       intake event · `ezra bench` · tests
```

## What each scorer checks

| Kind | Gates (hard: comes from an existing rule) | Warnings (reference checklist) |
|---|---|---|
| Acceptance Criteria | intake's `problems_with()` (count 2–8, ids, a critical, `check` only on deterministic) | 3–6 criteria; title under 60 chars; description ≤ 3 sentences; vague wording; test criteria that name no call or code |
| Standards | every field and section in `standards/templates/standard-template.md`; valid enums; id letter matches scope; `active` needs a Guardian validation (D-006); pass and fail conditions not the same sentence negated | more than one sentence in Requirement; wording that rewards length; `user_confirmed` with no quoted words; missing Exceptions or Examples |
| Quality Rubric, answer | none: accuracy and usefulness need Guardian | preamble, sign-off, headings in a short answer, recap section |
| Quality Rubric, Guardian's review | structured JSON; current rubric version; a reason for every score (GRD-2); known agent checks; grade equals `rubric.grade()` of the scores | scores below 5 with no note |
| Model Evals | full record schema; model is an exact id in `pricing.yaml`; every case cost re-priced from its tokens; pass rate, total, cost per pass and failure counts re-computed; can't be `qualified` on < 3 runs (D-012) | < 3 runs with no note saying so |

`passed` means no gate failed. `clean` means no gate and no warning. Best examples must be
clean; weak examples must not be.

## Where it's wired in now

1. **Intake (live, log only).** After a request passes intake, its criteria (code route) or its
   answer (direct route) is scored and an `intake_benchmark` event is saved with the warnings
   and sizes; `ezra trace` shows it. No repair, no extra call,
   no change in behaviour. This builds a record of how often intake misses the checklist, which
   M6's trace view can show.
2. **`ezra bench <kind> <file>`** scores any output: `criteria`, `standard`, `answer`, `review`,
   `eval`. `ezra bench references` checks that every reference example still scores as its label
   says. Exit code 0 on pass, 1 on a failed gate.
3. **Ready, not yet called:** `score_review` for Guardian's Tier 3 output (Tier 3 isn't live in
   Phase 1), `score_eval` for the Phase 6 eval runner, `score_standard` for the Phase 3 Standards
   library (it can already lint `standards/private/`).

## Tuning v2 (2026-11-21, approved by the user)

Grounded in Ezra's first 8 real intakes (6 coding tasks, 2 direct answers, Nov 20-21): 0 needed
a repair, all 6 coding tasks passed Guardian first time with every criterion met, criteria per
task were 6-8. `config/benchmarks.yaml` is now version 2.

| # | Item | What changed |
|---|---|---|
| 1 | Word lists | Vague phrases 11 → 34 (the usual requirements "weak words"); quoted strings and code spans are blanked before matching. Preambles are looked for in the first sentence only; 7 more sign-offs. 0 hits on the 38 real criteria. |
| 2 | "Concrete" test criterion | Needs something to exercise (a call, code span or quoted input) **and** an observable result (`result_words`, `==`, `->`). Fixes the one false warning on real data (longest_word AC6). |
| 3 | Headings in short answers | Still 300 words (about one 80x24 terminal screen), counting prose only: code blocks don't count. |
| 4 | Warnings blocking or fixing | Unchanged: log only. A warning type may be proposed for promotion only after ≥ 20 scored coding tasks, and only if tasks with it end in REVISE, ESCALATE or a failed hidden test at least twice as often as tasks without it. Promotion is a Guardian rule change (D-009 Level 1). |
| 5 | Wiring | Now: `ezra trace` shows the `intake_benchmark` line; direct answers are scored too (`scored: quality-rubric`). Later: Tier 3 runs `score_review` on Guardian's own JSON (failed gate → one repair, then the Guardian-failed path; never changes a verdict); the Phase 6 eval runner runs `score_eval` before saving a record (failed gate → not saved, run reports an error). |
| 6 | Example in intake's prompt | Repairs were 0/8, so the A/B measures criteria count, warnings, output tokens and cost instead. `ezra intake-ab estimate|run|report`: the 10 progressive-learning task descriptions × 2 arms (`control`, `example`) × 3 runs = 60 intake calls, about $0.60, capped by `--max-usd`. Run it after the progressive-learning pilot. Adopt the example only if criteria and output tokens go down with no rise in repairs. |
| 7 | Criteria count | `deterministic` criteria are free checks (D-007), so only the others count toward 3-6. On real data 2 of 6 tasks still warn (7 test criteria each), down from 5 of 6. |

Still guesses (Standards, not yet used live): the length-phrase list and "more than one sentence
in Requirement means more than one requirement".

## What it deliberately doesn't do

- **Judge meaning.** Invented scope, wrong facts or a bad approach need Guardian. These checks
  only catch what text rules can catch.
- **Change any verdict.** Nothing here feeds the D-002 table, and intake still repairs only on
  `problems_with()`. Making a warning block anything would be a Guardian rule change (D-009
  Level 1), so it's the user's call.
- **Put examples into prompts.** Adding the best example to intake's system prompt might cut
  repairs, but it costs ~600 input tokens per call (cached). That is a good fit for the
  controlled-experiment setup in D-012, not a default.

## Proposed decision (number at merge)

**Benchmarks score outputs deterministically against the reference outputs.** Each kind in
`docs/reference-outputs/` gets a zero-cost scorer with hard gates (from existing rules only) and
soft warnings (from the reference checklists). The reference examples double as the scorers'
tests. Scores are logged and shown; they never change a verdict or trigger a repair unless the
user decides so later. Thresholds live in `config/benchmarks.yaml`, versioned, and every score
records the version.

## Possible next steps

- Run `ezra intake-ab run --max-usd 1 --confirm` once the progressive-learning pilot is done.
- Call `score_review` inside Tier 3 when it goes live (item 5 above).
- Use `score_eval` as the eval runner's output validator in Phase 6 (item 5 above).
- Revisit item 4 after 20 scored coding tasks.
