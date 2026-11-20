# Ezra — Decision Log

Decisions that change or clarify the original spec (Google Doc "A.I. Agent execution").
Where this log and the spec disagree, this log wins.

Status values: **Accepted** (decided by the user) · **Proposed** (recommended, awaiting the user's decision).

| ID | Decision | Status |
|----|----------|--------|
| D-001 | Split "benchmark" into four named concepts | Accepted |
| D-002 | One verdict model, with a mapping between layers | Accepted |
| D-003 | Gate-based passing instead of a weighted-average threshold | Accepted |
| D-004 | Three separate loop counters (no clash between Tester and Guardian) | Accepted |
| D-005 | Rename Code Joe's "Creator" sub-agent to **Builder** | Accepted |
| D-006 | Ezra approves autonomously | Accepted |
| D-007 | Risk-tiered Guardian review | Accepted |
| D-008 | Build order flipped: slice → traces → standards | Accepted |
| D-009 | Which decisions come back to the user, by importance | Accepted |
| D-010 | Runtime and scope: local Python, Claude-only, Learner logs Ezra only | Accepted |

---

## D-001 — Four concepts replace the word "benchmark"  *(Accepted)*

The spec used "benchmark" for three different things. From now on the bare word is retired, and each concept has its own name, owner and lifetime.

| Name | What it is | Scope | Written by | Lifetime | Spec section it replaces |
|------|-----------|-------|------------|----------|--------------------------|
| **Standards** | Durable, reusable requirements: "how the user wants things done" | Global · Department · Project | User (confirmed) or Learner (proposed) → Guardian validates → Ezra activates | Versioned, long-lived | Standards Library + global/department/project "benchmarks" (§4.2, §4.3, the "first prompt") |
| **Acceptance Criteria** | What "done" means for *this one task*, derived from the request + applicable Standards | Task | Ezra, at task creation | Snapshotted into the TaskEnvelope; frozen for the task | Task-specific "benchmark snapshot" (§4.3) |
| **Quality Rubric** | The scoring instrument Guardian uses to grade outputs (7 categories, 1–5 anchors) | Applied to any text output | Ezra owns; changes via governance | Versioned | "Global Text Output Quality Benchmark" |
| **Model Evals** | Test suites that qualify a model for a specific operation | Model × operation | Ezra owns; Learner proposes cases | Versioned; results immutable | Model Routing addendum "benchmark suites" |

**Single severity scale** (used by Standards, Acceptance Criteria and Rubric failures):

| Severity | Meaning | Effect |
|----------|---------|--------|
| `critical` | Violating it makes the output unusable, unsafe or misleading | Automatic fail regardless of score |
| `major` | Materially reduces usefulness or correctness | Must be fixed before PASS |
| `minor` | Noticeable but doesn't affect the outcome | Logged as a note; does not block |

The template's `critical/high/medium/low` scale is retired: `high` maps to `major`, and `medium` and `low` map to `minor`.

**Glossary of storage names (for later code):** `standards`, `standard_versions`, `acceptance_criteria`, `rubrics`, `rubric_versions`, `model_evals`, `model_eval_results`.

---

## D-002 — Verdict mapping  *(Accepted)*

The documents used three vocabularies. They now live at **three separate layers**, and only one layer controls flow.

| Layer | Who produces it | Values | Controls flow? |
|-------|-----------------|--------|----------------|
| 1. **Test result** | Tester (inside Code Joe) | `tests_pass` · `tests_fail` · `tests_error` | Only inside Code Joe (internal iterations, see D-004) |
| 2. **Quality grade** | Guardian, from the Rubric | `excellent` · `pass` · `conditional` · `fail` | No. It's an input to Layer 3 and is recorded for Learner and Model Evals |
| 3. **Guardian verdict** | Guardian | `PASS` · `REVISE` · `HOLD` · `ESCALATE` | **Yes. It is the only verdict that moves a task** |

The old Code Joe diagram labels map as **Pass** → `PASS`, **Correction** → `REVISE` and **Fail** → `ESCALATE`.

### Verdict decision table

Guardian evaluates the rules **top to bottom; the first match wins**.

| # | Condition | Correction budget left? | Guardian verdict |
|---|-----------|------------------------|------------------|
| 1 | An authorization or permission requirement is unresolved | any | `HOLD` |
| 2 | Issue cannot be safely fixed automatically (ambiguous request, needs user input, irreversible action already taken) | any | `ESCALATE` |
| 3 | Any `critical` failure, including an unmet `critical` Acceptance Criterion | yes | `REVISE` |
| 4 | Any `critical` failure, including an unmet `critical` Acceptance Criterion | no | `ESCALATE` |
| 5 | *(graded outputs only)* Grade `fail` | yes | `REVISE` |
| 6 | *(graded outputs only)* Grade `fail` | no | `ESCALATE` |
| 7 | Any unmet `major` Acceptance Criterion or `major` finding (e.g. a broken test run), **or** *(graded outputs only)* grade `conditional` | yes | `REVISE` |
| 8 | Any unmet `major` Acceptance Criterion or `major` finding (e.g. a broken test run), **or** *(graded outputs only)* grade `conditional` | no | `ESCALATE` (Ezra may deliver with caveats) |
| 9 | Everything else: no critical failures, all `major` criteria met, and *(if graded)* grade `pass` or `excellent` | any | `PASS` (any `minor` issues attached as notes) |

**Major findings (approved by the user 2026-11-20):** rows 7–8 also count a `major` *finding* (a problem outside the criteria, e.g. a broken test run) the same as an unmet `major` criterion. Implemented in `guardian/verdict.py`.

**Unverifiable counts as unmet.** If Guardian can't find evidence that a criterion is met (`cannot_verify`), it's treated as `unmet` at that criterion's severity. Evidence beats assumption.

**What happens after each verdict:**
- `PASS`: the output returns to Ezra, which delivers it.
- `REVISE`: Guardian sends structured repair instructions to the originating department and the task's correction cycle is consumed.
- `HOLD`: execution pauses until the authorization is resolved, then the same review resumes. This does not consume the correction cycle.
- `ESCALATE`: the issue returns to Ezra with the evidence. Ezra either delivers with clear caveats, asks the user, or stops.

**For outputs that get no Rubric grade** (Tier 1 and Tier 2 reviews, see D-007), the grade-only conditions are skipped: rows 5–6 entirely, and the grade half of rows 7–9. The verdict then comes from critical failures and Acceptance Criteria only.

---

## D-003 — Gate-based passing  *(Accepted)*

**Problem.** The formula is `Σ weight × rating / 5`, so a 4/5 ("Strong: correct, complete, useful") in every category scores exactly **80**, which lands in *Conditional*. Passing at 85 needs about a 4.25 average, meaning several 5/5 ("Exceptional") ratings. LLM graders also rarely give 5s. In practice almost every good output would use up the single correction cycle, which doubles Guardian's token cost, and many would escalate to Ezra. The strictness lands on presentation polish rather than on correctness.

**Proposal.** The grade comes from **gates**, not the average. The weighted score is kept for trends and Model Evals, but it doesn't decide pass or fail.

| Grade | Rule |
|-------|------|
| `fail` | Any critical failure, **or** any core category (A Accuracy, B Instruction Adherence, C Task Achievement) ≤ 2 |
| `conditional` | No critical failures, but a core category = 3, **or** any other category ≤ 2 |
| `pass` | No critical failures, core categories (A, B, C) all ≥ 4, other categories all ≥ 3 |
| `excellent` | Meets `pass` **and** weighted score ≥ 90 (informational only) |

Strictness stays where it matters (accuracy, following instructions, actually solving the problem). It relaxes where it doesn't (formatting).
Thresholds get recalibrated against real outputs in Phase 2 (D-008).

---

## D-004 — Three separate loop counters  *(Accepted)*

**Problem.** Code Joe has an internal Tester→Creator fix loop, and Guardian can also issue a correction. Spec §10.3 makes them share one budget. A single failing test inside Code Joe would therefore use the task's only correction, so any issue Guardian later found could only be escalated.

**Proposal.** Ezra tracks three counters in the TaskEnvelope, and each has a different job:

| Counter | What it counts | Limit | Consumed by |
|---------|----------------|-------|-------------|
| `infra_retries` | Network, timeout or transport failures | 2 per call, with idempotency keys | Gateway / MCP layer |
| `internal_iterations` | A department fixing its own work *before* submitting (e.g. Tester → Builder) | 2 per submission | Code Joe (and later any department with an internal check) |
| `correction_cycles` | Guardian sending a submitted output back (`REVISE`) | **1 per task, shared across departments** | Guardian only |

- A department's work only becomes a **submission** when it reaches Guardian. Everything before that counts as production, not correction.
- After a `REVISE`, Code Joe may run its Builder → Tester loop once more (`internal_iterations` resets to a cap of 1 for the revision).
- Worst case for a coding task is 3 Builder runs before the first submission, plus 2 on revision. That's bounded and predictable.
- This replaces spec §10.3. The "never use model switching to dodge the limit" rule from the routing addendum still applies, now to all three counters.

---

## D-005 — Creator renamed to Builder  *(Accepted)*

- Code Joe's sub-agents are **Builder** and **Tester**. Builder writes code, Tester checks it.
- **Artifact Creator** keeps its name. It is the MCP tool interface for external actions.
- The department is spelled **Code Joe** everywhere ("Coder Joe" is retired).
- Rubric agent-specific rows are corrected:

| Agent | Specialized evaluation |
|-------|------------------------|
| Ezra | Intent recognition, context management, task routing |
| Code Joe | Planning quality, architecture, correct delegation |
| Builder | Code correctness, instruction adherence, changed-files reporting |
| Tester | Test coverage, defect identification, reproducibility |
| Artifact Creator | Action correctness, receipt completeness, permission compliance (mostly deterministic) |
| Guardian | Evaluation accuracy, error detection, false-approval prevention |
| Learner | Analytical accuracy, evidence quality, explicit-vs-inferred separation |

The Model Evals list in the routing addendum renames "Creator" to "Builder".

---

## D-006 — Ezra approves autonomously  *(Accepted)*

Ezra activates validated Standards, Rubric changes and model approvals without waiting for the user.

Safeguards already in the spec, now required:
1. Nothing is activated without a Guardian validation record.
2. Every activation is versioned and can be rolled back in one step.
3. **Added:** Ezra writes every activation to a change log and includes it in a digest to the user. The user can roll back any change, so autonomy never means the user can't see what changed.
4. **Added:** changes to **Guardian's own Rubric or verdict rules** can't be validated by Guardian alone, because that would mean grading its own homework. They need Model-Eval evidence (Guardian's false-approval rate before and after the change).

---

## D-007 — Risk-tiered Guardian review  *(Accepted)*

**Goal:** keep Guardian independent while avoiding a second model call on every output.

**Definition of a "material" output:** anything that (a) persists (files, code, documents), (b) leaves the system (emails, shares, calendar invites), (c) changes Standards, the Rubric or routing, or (d) is presented to the user as a finished deliverable. Conversational replies and lookups are not material.

| Tier | When | How Guardian reviews | Model cost |
|------|------|---------------------|------------|
| 0: none | Not material (chat, quick answers, status) | No review | 0 |
| 1: deterministic | Outputs with machine-checkable evidence: Artifact Creator receipts (does the resource exist? does the ID match?), schema-valid results, test/lint/type results | Code checks only | 0 |
| 2: checklist | Routine material outputs | Cheap model; each **Acceptance Criterion** judged yes/no with cited evidence; no 7-category scoring | Low |
| 3: full rubric | High-stakes: code going to main, anything external and irreversible, Learner reports that change Standards, changes to routing | Strong model; full Rubric + Acceptance Criteria | High |

**Efficiency techniques used at every tier:**
1. **Deterministic first, short-circuit.** If tests fail or the schema is invalid, the verdict is decided without any model call.
2. **Review evidence, not transcripts.** Guardian receives the StandardDepartmentResult, diffs and test output, never the department's full conversation.
3. **Binary checklists over 1–5 scoring** at Tier 2. They are cheaper and more consistent.
4. **Prompt caching.** Guardian's instructions, Rubric and Standards are static, so they're cached and only the evidence is new per call.
5. **Pre-execution review for irreversible actions.** Guardian checks the *planned* email or share (recipients, content) before Artifact Creator runs it, because rejecting after the fact can't undo it.
6. **Earned trust (later).** Once a department/operation pair has a strong pass record, its Tier-2 reviews can be sampled (e.g. 1 in 5) instead of run every time. Any failure restores full review.
7. **Offline full scoring.** For Learner and Model Evals, full-rubric scoring of sampled outputs can run later at batch pricing, as telemetry rather than as a gate.

Tier assignment is a deterministic rule on the output type and the action flags in the TaskEnvelope, not a model call.

---

## D-008 — Build order flipped  *(Accepted)*

Real execution traces come first, and Standards get written from the failures they show. The "first prompt" (a full benchmark template library) is deferred.

| Phase | Goal | Done when |
|-------|------|-----------|
| 1. Thin slice | User → Ezra → Code Joe (Builder + Tester) → Guardian (Tier 1 + Tier 2) → User, with the Model Gateway logging every call | One real coding task flows end-to-end with full traces and token counts |
| 2. Error analysis | Run 20–50 real tasks; read the traces; categorize failures | A written failure taxonomy exists |
| 3. Standards from evidence | Write the first Standards and Acceptance Criteria templates from the taxonomy; calibrate D-003 thresholds against real outputs | Standards library v1 + calibrated Rubric |
| 4. Learner | Interaction logging + daily report | First Guardian-validated report |
| 5. Artifact Creator | MCP server, starting with one namespace | Receipts verified at Tier 1 |
| 6. Model Evals & routing | Registry, evals, router | First model approved per operation from internal evidence |

---

## D-009 — Which decisions come back to the user  *(Accepted)*

Ezra decides on its own by default (D-006). This matrix lists the exceptions, ranked by importance.
**If Ezra isn't sure which level a decision belongs to, it uses the higher one.**

| Level | Ezra's behavior | Decisions at this level |
|-------|-----------------|-------------------------|
| **1. Ask first** (blocking) | Stops and waits for an explicit yes from the user | • Anything irreversible or leaving the system: sending email or messages, sharing files outside, deleting files or data, invites to other people, anything involving money<br>• Pushing code to a remote, or merging into a project's main branch<br>• Changing Guardian's Rubric or verdict rules, the loop limits (D-004), permission or security policy, or **this matrix**<br>• Sending data to a new external service or a non-Claude provider<br>• A single task expected to cost more than **$2**, or daily spend passing **$10** *(defaults; the user can change them)*<br>• An `ESCALATE` that Ezra can't resolve by delivering with caveats |
| **2. Do, then tell right away** | Acts, then notifies the user immediately with a one-step rollback | • Activating a Standard that Learner **inferred** (not one the user confirmed)<br>• Approving a model for a new operation, or retiring or demoting one<br>• Changing the routing policy<br>• Any rollback Ezra performs itself |
| **3. Do, include in daily digest** | Acts; summarized once a day | • Learner reports applied to the user profile<br>• Activating a Standard the user explicitly confirmed<br>• Model Eval results and qualification reports<br>• A department earning or losing sampled-review trust (D-007 #6)<br>• Weekly spend and token trends |
| **4. Just do** (log only) | Acts; available in traces, never surfaced | • Per-task model routing, review tier assignment, retries, internal iterations, context retrieval choices |

Rules for the matrix itself:
- Only the user can move an item to a *lower* level. Ezra may propose a move, but never makes one itself.
- Ezra may move an item to a *higher* level on its own (for example, after a bad outcome) and says so in the digest.
- Recorded in `approval_records` with the level, the decision and the user's response.

---

## D-010 — Runtime and scope  *(Accepted)*

| Topic | Decision | Status |
|-------|----------|--------|
| Runtime | Local Python app on the user's Mac | Accepted |
| Model providers | Claude only (Anthropic API). The Model Gateway still keeps a provider interface so others can be added later. | Accepted |
| Learner's data | Logs **only interactions with Ezra**, not the user's other AI tools | Accepted |
| First milestone | Thin working slice (D-008 Phase 1) | Accepted |
| Interface for the slice | Command line (`ezra "…"` plus an interactive chat mode). A web or voice interface can come later on top of the same core. | Accepted |
| Database for the slice | **SQLite** (one local file, no server, and LangGraph has a SQLite checkpointer). Move to Postgres only if a real need appears. | Accepted |

## Still open

- Where the Claude routing dataset files (`routing_policy.json`, `task_routing.csv`, …) are. They're needed in Phase 6, not before.
- Eval environment, re-eval frequency, eval budget limits (Phase 6).
- Database choice, eval environment, re-eval frequency, eval budget limits.
