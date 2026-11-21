# Reference output: Standards

**Produced by:** the user (stated) or Learner (proposed, from Phase 4), written up by Ezra.
**Read by:** Ezra (snapshots applicable Standards into each task's Acceptance Criteria),
Guardian (validates proposals; checks compliance), every department it applies to.
**Governed by:** D-001, D-006, D-008, D-013, [standards/README.md](../../standards/README.md),
[the template](../../standards/templates/standard-template.md).

## What "best" means here

A Standard is read by every task it applies to, for as long as it's active. Its size is paid
on every one of those tasks, and its vagueness is paid every time Guardian has to guess. The
best Standard is **one requirement that Guardian can rule on from evidence, in as few words as
that takes.**

| Property | Best output | Why it saves tokens |
|---|---|---|
| One requirement | A single observable rule | Splits cleanly into one Acceptance Criterion; no partial passes |
| Observable | Pass and fail conditions name what Guardian looks at | Ruled on by a checklist (Tier 2) or code (Tier 1), not the full rubric |
| Evidence named | `required_evidence` says exactly what proves it | No `cannot_verify`, so no wasted correction cycle |
| Honest source | `user_confirmed` only for the user's words; otherwise `system_defined` / `learner_inferred` | Prevents rework when an inferred rule turns out wrong |
| Short | The template's sections, one or two lines each | It's re-read on every task in scope |
| Scoped | Narrowest `scope` and `applies_to` that fit | Departments it doesn't apply to never load it |

## Same intent, two outputs

Intent: agents should be honest about what they did and didn't finish.
Both examples are **illustrative** (not an active Standard), using `source: system_defined`.

### Weak

<!-- example: standards/weak -->
```markdown
---
id: STD-G-002
title: Transparency, honesty and clear communication
version: 1
status: active
scope: global
applies_to: [all]
severity: critical
source: user_confirmed
---

## Requirement
All agents must always be fully transparent and honest in everything they do. They should
communicate clearly and professionally, explain their reasoning in detail, make sure the user
always understands what is happening, avoid making mistakes, and be helpful at all times.
Outputs should be high quality and well formatted, and agents should be proactive in
suggesting improvements wherever possible.

## Rationale
Transparency is important for trust. Users need to be able to rely on the system and
understand what it is doing at every step of the process.

## Passing conditions
The agent is transparent and honest.

## Failure conditions
The agent is not transparent or honest.
```

What's wrong:
- **Seven requirements in one** (honesty, clarity, detailed reasoning, no mistakes, helpfulness,
  formatting, proactivity). A partial pass can't be expressed, so Guardian must fail or ignore it.
- **Circular conditions:** "transparent" passes if "transparent". Nothing to check, so every
  ruling is `cannot_verify`.
- **"Explain their reasoning in detail" pushes outputs longer** for no measurable gain.
- **Governance errors:** claims `user_confirmed` for words the user never said; `active` with
  no Guardian validation (D-006); missing `verification`, `required_evidence`, dates.

### Best

<!-- example: standards/best -->
```markdown
---
id: STD-G-002
title: Report what was not done
version: 1
supersedes: null
status: draft
scope: global
applies_to: [all]
project: null
severity: major
source: system_defined
verification: inspection
required_evidence: The output's final summary, compared with the task's Acceptance Criteria.
created_at: 2026-11-21
last_reviewed: 2026-11-21
guardian_validation: null
---

## Requirement
A delivered output names every Acceptance Criterion it did not meet, or states that all were met.

## Rationale
Silent gaps are found later, at higher cost, by the user.

## Passing conditions
The final summary lists each unmet criterion by id, or says "all criteria met".

## Failure conditions
Any criterion Guardian rules unmet is absent from the summary.

## Exceptions
Tier 0 outputs (no criteria).

## Examples
- Approved: "Done except AC3 (punctuation): left attached; confirm?"
- Rejected: "All done!" when AC3 is unmet.
```

Why it's best: one rule, a mechanical pass/fail (compare two lists), named evidence, an honest
source and `draft` status. It is slightly *longer* than the weak version, because it carries
every required field, but the weak one can't be validated or enforced at all, so its tokens buy
nothing. "Shortest" always means shortest **that fully meets the requirements**.

## Checklist for writing a Standard

- [ ] Exactly one requirement; split anything with "and".
- [ ] Pass and fail conditions name something Guardian can see.
- [ ] `required_evidence` is specific.
- [ ] `source` is honest; `status: draft` until validated.
- [ ] Nothing that rewards length ("in detail", "comprehensive") unless the user asked for it.
- [ ] Narrowest scope that fits.

## Sources

See [model-evals.md § Sources](model-evals.md#sources) for the shared evidence behind
"shortest output that fully meets the requirements".
