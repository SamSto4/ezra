---
id: STD-G-000            # STD-<G|D|P>-<number>: G = global, D = department, P = project
title: Short descriptive name
version: 1
supersedes: null         # the previous version's id@version, kept for rollback
status: draft            # draft | active | deprecated | archived
scope: global            # global | department | project
applies_to: [all]        # all, or any of: ezra, code_joe, builder, tester, guardian, learner, artifact_creator
project: null            # set only when scope is project
severity: major          # critical | major | minor (D-001)
source: user_confirmed   # user_confirmed | system_defined | learner_inferred
verification: inspection # test | inspection | deterministic
required_evidence: What Guardian must see to call this met.
created_at: YYYY-MM-DD
last_reviewed: YYYY-MM-DD
guardian_validation: null # validation record id; required before status can be active (D-006)
---

## Requirement
What exactly must be done. One requirement per Standard.

## Rationale
Why it exists. For user_confirmed Standards, quote or paraphrase the user's words.

## Passing conditions
Observable conditions that show it was met.

## Failure conditions
What counts as not meeting it.

## Exceptions
When it does not apply.

## Examples
- Approved: …
- Rejected: …
