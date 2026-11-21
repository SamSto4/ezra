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

1. **Intake (live, log only).** After a `code` request passes intake, its criteria are scored and
   an `intake_benchmark` event is saved with the warnings and sizes. No repair, no extra call,
   no change in behaviour. This builds a record of how often intake misses the checklist, which
   M6's trace view can show.
2. **`ezra bench <kind> <file>`** scores any output: `criteria`, `standard`, `answer`, `review`,
   `eval`. `ezra bench references` checks that every reference example still scores as its label
   says. Exit code 0 on pass, 1 on a failed gate.
3. **Ready, not yet called:** `score_review` for Guardian's Tier 3 output (Tier 3 isn't live in
   Phase 1), `score_eval` for the Phase 6 eval runner, `score_standard` for the Phase 3 Standards
   library (it can already lint `standards/private/`).

## Guesses to revisit (all marked GUESS in config/benchmarks.yaml)

- The vague-phrase, length-phrase, preamble and sign-off word lists. They were taken from the
  weak examples, so they will miss other phrasings and may flag a legitimate use.
- "A test criterion is concrete if it names a call or has a code span." Cheap, and it catches
  every weak criterion in the reference, but it can't tell a precise sentence from a vague one
  that happens to contain backticks.
- "More than one sentence in Requirement means more than one requirement."
- The 300-word line under which an answer shouldn't need headings.

Measure these once M6 traces have real intake outputs: count how often each warning fires and
check a sample by hand.

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

- Show `intake_benchmark` warnings in `ezra trace` (M6).
- Call `score_review` inside Tier 3 when it goes live, and treat a failed gate as Guardian
  infrastructure failure.
- Use `score_eval` as the eval runner's output validator in Phase 6.
- Experiment: intake with and without the best example in its prompt; compare repair rate and
  cost per successful task.
