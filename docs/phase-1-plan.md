# Phase 1: Thin Working Slice

**Goal:** one real coding request flows end to end: **User → Ezra → Code Joe (Builder + Tester) → Guardian → User**. Every model call is logged, and every step lands in a trace we can read in Phase 2.
**Governed by:** [decisions.md](decisions.md) (D-001 to D-016).
**Status:** Approved. M1–M5 are done; see section 9.

---

## 1. What's in and what's out

| In Phase 1 | Deferred |
|------------|----------|
| CLI (`ezra ask`, `ezra chat`, `ezra trace`) | Web or voice interface |
| Ezra intake: route the request, write Acceptance Criteria, answer simple questions directly | Standards library, user profile, context retrieval (Phase 3) |
| Model Gateway: one entry point for every model call, with token, cost and latency logging and budget limits | Model Registry, Model Evals, dynamic router (Phase 6) |
| Code Joe as a LangGraph graph: plan → Builder and Tester → run → adjudicate → iterate | Code Joe on non-Python projects |
| Guardian Tier 1 (deterministic) and Tier 2 (checklist), the D-002 verdict table, the D-004 counters | Tier 3 full rubric, earned trust, offline scoring |
| SQLite store and readable traces | Postgres, object storage |
| Approval matrix: only the parts this slice can trigger (cost limits; code never leaves its branch) | The rest of D-009 (no external actions exist yet) |
| | Learner (Phase 4), Artifact Creator (Phase 5) |

**Why we build the loop ourselves (Messages API + LangGraph) instead of Anthropic's hosted Managed Agents:** LangGraph is a locked decision, everything runs locally, and the point is to learn how orchestration works by owning it. Managed Agents would host the loop for us, but would hide exactly the parts we want to understand.

---

## 2. How a request flows

```mermaid
flowchart TD
    U(["User runs ezra ask"]) --> IN["Ezra intake: 1 model call, structured output"]
    IN -->|direct| ANS["Answer directly, Tier 0, no review"] --> OUT(["User"])
    IN -->|unsupported| NA["Explain it is not built yet"] --> OUT
    IN -->|code| ENV["Create TaskEnvelope: task_id, Acceptance Criteria, counters, budget"]
    ENV --> WT["Create git worktree on branch ezra/task_id"]
    WT --> PLAN["Code Joe plans: steps + interface spec"]
    PLAN --> B["Builder implements from the interface spec"]
    PLAN --> TW["Tester writes acceptance tests from criteria + interface spec"]
    B --> RUN["Run tests + ruff in a sandboxed subprocess, no model"]
    TW --> RUN
    RUN -->|pass| PKG["Build StandardDepartmentResult"]
    RUN -->|fail and internal_iterations below 2| ADJ["Code Joe adjudicates: is the code wrong or the test wrong?"]
    ADJ -->|code| B
    ADJ -->|test| TW
    RUN -->|fail and cap reached| PKG
    PKG --> T1["Guardian Tier 1: deterministic checks"]
    T1 --> T2["Guardian Tier 2: each criterion yes or no, with evidence"]
    T1 -->|critical failure| V
    T2 --> V{"Verdict table D-002"}
    V -->|PASS| OUT2(["User: summary, branch name, cost"])
    V -->|REVISE| B
    V -->|ESCALATE| OUT3(["User: what failed, with evidence"])
```

`HOLD` isn't shown here because it can happen at *any* model call, not only at review (see section 4, Cost limits).

### Three design choices worth understanding

**1. A shared interface spec.** Code Joe's plan includes an interface spec: which files, functions and signatures will exist. Builder and Tester both receive it. Without it, Tester has to guess names and iterations get wasted on naming mismatches instead of real bugs.

**2. Tester independence.** Tester writes acceptance tests from the Acceptance Criteria and the interface spec, *without seeing Builder's code*. That keeps tests from simply confirming whatever Builder happened to write.
- Builder **cannot write to Tester's test files**; the path guard rejects it. Otherwise Builder could "pass" by weakening the tests.
- When tests fail, Code Joe **adjudicates**: either the code is wrong (back to Builder) or the test is wrong (back to Tester). Both count as internal iterations.

**3. REVISE goes to Builder, and the tests are frozen.** After Guardian says `REVISE`, Builder gets Guardian's repair instructions and fixes the code. The plan and the tests are *not* regenerated, so the goalposts can't move between attempts. Builder then gets **one** more run → test cycle (D-004).

---

## 3. Model routing table (fixed for Phase 1)

This table stands in for the Model Router until Model Evals exist (Phase 6). The picks come from your routing dataset and your rule that Code Joe runs on a stronger model than Builder and Tester.

| Operation | Model | Effort | Why |
|-----------|-------|--------|-----|
| `ezra.intake` (route, criteria, direct answers) | `claude-sonnet-5-5` | medium | General assistant work (dataset T09); one call does all three |
| `code_joe.plan` | `claude-opus-5-5` | medium | Ambiguous multi-file coding (T17); must be above Builder |
| `code_joe.adjudicate` | `claude-opus-5-5` | low | Short judgement call: is the test or the code at fault? |
| `builder.implement` | `claude-sonnet-5-5` | medium | Well-scoped coding (T16) |
| `tester.write_tests` | `claude-sonnet-5-5` | medium | Test generation |
| `guardian.tier2` | `claude-opus-5-5` | low | Code review (T21). A different model from Builder, so their blind spots are less likely to line up |

It lives in `config/routing.yaml`, so changing a model means editing config, not code.

**Gateway behavior on every call:**
- Adaptive thinking.
- Effort taken from the table.
- Prompt caching on static system prompts. Cache-read tokens are logged from M2 on, so we *measure* the savings. Short prompts may fall under the cache minimum, so none are assumed.
- Server-side refusal fallbacks turned on.
- Bounded infrastructure retries.
- One `ModelInvocation` row per call (the schema from the routing addendum §11).

---

## 4. Safety rails in the slice

| Rail | How it's enforced |
|------|-------------------|
| **Code Joe only touches its own copy** | Every task gets a fresh git worktree on branch `ezra/<task_id>`. The file tools resolve real paths (so symlinks can't escape) and reject anything outside the worktree. Builder is also blocked from Tester's test files. |
| **No arbitrary shell for the models** | Builder and Tester get file tools only (read, list, write, edit). They can't run commands. |
| **Running tests is sandboxed, not airtight** | `pytest` and `ruff` run as a subprocess with cwd set to the worktree, a **scrubbed environment** (no `ANTHROPIC_API_KEY` or other secrets), and a timeout. **Residual risk:** running the tests means running Builder's code with your user's file permissions. In Phase 1 that's acceptable, because tasks target the `playground/` repo and you review the code before merging. A container sandbox is a later hardening step. |
| **Code never leaves its branch** | Phase 1 has no push or merge code at all. At PASS, Ezra reports the branch name and the diff summary; *you* merge if you want it (D-009 Level 1). That's also why Guardian Tier 3 (D-007, "code going to main") isn't needed yet. |
| **Cost limits** | Before each call, the Gateway checks: *actual spend so far + the worst case for this call* (counted input tokens + `max_tokens` × output price). If that would pass **$2** for the task or **$10** for the day, the Gateway first shrinks the call to fit: a smaller output limit, and lower effort if it shrinks below half (D-016). Only if even that can't fit does the task pause with `HOLD` and Ezra asks you. LangGraph's interrupt + SQLite checkpointer should let the graph pause at any node and resume after your answer; **this is verified at M4**, and if it doesn't hold, the fallback is to end the task cleanly with a resumable checkpoint. |
| **Loop limits** | `infra_retries` ≤ 2 per call. `internal_iterations` ≤ 2 before the first submission and ≤ 1 after a REVISE. `correction_cycles` ≤ 1 per task. All of them are held in the TaskEnvelope. |
| **Secrets** | The API key comes from your environment or `ant auth login`. It is never written to the database, the traces or the test subprocess. |

---

## 5. Contracts (the core shapes)

- **AcceptanceCriterion:**
  - `id`
  - `text`
  - `severity`: `critical`, `major` or `minor` (D-001)
  - `verification`: `test` (checked by a test), `inspection` (checked by Guardian reading the diff) or `deterministic` (checked by code, e.g. "ruff passes")
  - `required_evidence`
- **TaskEnvelope:** the spec's §9.1 fields, plus the Acceptance Criteria snapshot, the three D-004 counters and the budget.
- **StandardDepartmentResult:** the spec's §9.2 fields, plus the interface spec, changed files, test results and the worktree branch.
- **GuardianReview:**
  - the spec's §8.5 fields
  - `tier`
  - per-criterion result (`met`, `unmet` or `cannot_verify`) with evidence
  - verdict
- **ModelInvocation:** the routing addendum's §11 record, plus cache-read tokens.

---

## 6. Repository layout

`Ezra A.I.` becomes its own git repo. **`playground/` is a separate git repo** nested inside it but ignored by Ezra's repo, so Code Joe's worktrees are of the playground, never of Ezra itself. Runtime data stays out of version control.

```
Ezra A.I./                   ← git repo (Ezra's own code)
├── .gitignore               playground/, .ezra/, .venv/
├── docs/                    decisions.md, phase-1-plan.md
├── pyproject.toml
├── config/
│   ├── routing.yaml         operation → model + effort
│   └── limits.yaml          budgets, loop caps, test timeout
├── src/ezra/
│   ├── cli.py               ezra ask | chat | trace
│   ├── contracts.py         Pydantic models from section 5
│   ├── intake.py            Ezra intake
│   ├── gateway.py           the only place that calls Claude
│   ├── store.py             SQLite: tasks, invocations, results, reviews, events
│   ├── code_joe/
│   │   ├── graph.py         LangGraph graph + state
│   │   ├── builder.py
│   │   ├── tester.py        test writing + sandboxed test run
│   │   └── workspace.py     worktrees + path guard
│   └── guardian/
│       ├── tier1.py         deterministic checks
│       ├── tier2.py         checklist review
│       └── verdict.py       the D-002 table as pure code
├── tests/                   Ezra's own unit tests
├── .ezra/                   (ignored) ezra.db, worktrees/
└── playground/              (ignored, own git repo) demo project for Code Joe
```

---

## 7. Build steps

The steps are ordered so everything that needs **no API access** comes first. We can start before your credentials are set up.

| # | Step | Needs API? | Done when |
|---|------|-----------|-----------|
| M1 | **Foundation:** git init, pyproject, contracts, SQLite store, `verdict.py`, Guardian Tier 1, workspace + path guard, `playground/` repo | No | Unit tests cover every row of the D-002 table, every D-004 counter edge case, and path-guard escapes (including `..` and symlinks) |
| M2 | **Gateway + CLI:** model calls, logging, cost estimate, budget check | Yes | `ezra ask "what's 2+2"` answers, and its tokens (including cache reads) and cost are in the database |
| M3 | **Ezra intake:** structured output for route + Acceptance Criteria | Yes | A code request produces a TaskEnvelope with typed criteria; a simple question is answered directly |
| M4 | **Code Joe graph:** plan + interface spec → Builder and Tester → sandboxed run → adjudicate → iterate; budget HOLD and resume | Yes | A small task in `playground/` ends with passing tests on its own branch, and a forced budget overrun pauses and resumes |
| M5 | **Guardian Tier 2 + REVISE** | Yes | A deliberately flawed output triggers REVISE once, then PASS or ESCALATE, never a third attempt |
| M6 | **Trace viewer + first real task** | Yes | `ezra trace <task_id>` shows every step, model, token count, cost and verdict for one real task |

**Phase 1 is complete when:**
- One real coding task runs end to end under one `task_id`.
- 100% of model calls go through the Gateway and are logged.
- The file tools never write outside the worktree, which the M1 tests prove.
- Code never leaves its branch without you.
- The budget limits shrink a call to fit, or trigger `HOLD` (D-016).
- We have a **baseline cost and token count per successful task** to improve against.

---

## 8. Before we start

1. **API access (needed from M2).** Set `ANTHROPIC_API_KEY` in your shell profile, or install the Anthropic CLI and run `ant auth login`. Don't paste the key into chat.
2. **Python 3.14** is installed. If LangGraph doesn't support it yet, we'll see at M1 and install 3.13 alongside it.
3. **Environment:** a standard `venv` and `pip`, so nothing new to install.

---

## 9. Progress

**M1, done (2026-11-20).** 80 unit tests pass and ruff is clean. LangGraph runs on Python 3.14.

**Carried into M4:**
- Before submitting, Code Joe checks that every test-verified criterion has an acceptance test. Otherwise a missing test would REVISE back to Builder, who can't write tests, and the task would always ESCALATE.
- Worktrees live under Ezra's folder, so the sandboxed pytest and ruff runs must pass the target repo's root and config explicitly. Otherwise they could pick up Ezra's own `pyproject.toml`.
- Builder and Tester will run in parallel and share one SQLite connection. Use one connection per thread, and make the budget check and the spend atomic. Otherwise two calls can both pass the check and together overspend.
- Answering a HOLD (approve or reject, then resume) is built with the LangGraph interrupt in M4. In M2 a HOLD only stops the call and stores a pending approval.

**M2, done (2026-11-20).** The Gateway (`gateway.py`), prices (`config/pricing.yaml` and `pricing.py`), a core module (`core.py`) and a thin CLI (`ezra ask`, `ezra approvals`). 100 tests pass and ruff is clean.
- **Live check:** `ezra ask "what's 2+2"` answered "2 + 2 = 4" on Sonnet 5.5. The logged row shows 55 input tokens, 11 output tokens and $0.000220, which matches a hand calculation. Cache read was 0, as expected, because the prompt is under the 512-token caching minimum.
- **Forced HOLD:** with a $0.001 budget on a throwaway database, the call stopped before reaching the model, and a pending Level 1 `budget_hold` approval was stored.
- **Probed before building:** the request shape (adaptive thinking, effort, `fallbacks: "default"` under `server-side-fallback-2026-07-01`, streaming) is accepted by both Sonnet 5.5 and Opus 5.5. Fallback targets are Sonnet 5.5 → Sonnet 5, and Opus 5.5 → Opus 4.8 or Opus 5.
- **Cost rules:**
  - Each attempt in `usage.iterations` is priced at its own model.
  - A model with no price is never counted as $0; the budget falls back to the worst-case estimate.
  - The worst case prices input at the cache-write rate and the full `max_tokens` at the most expensive model the call could land on.
  - A call without a task is capped at the per-task budget.
- **D-011 rules in place:**
  - Every call writes `model_call_started` and `model_call_finished` events.
  - A HOLD is stored in `approval_records`.
  - The CLI only prints; the logic lives in `core.py`.
- **Failure handling:**
  - Missing credentials give a clear message, not a traceback.
  - A call the API rejected (4xx/5xx) is booked at $0.
  - Timeouts and dropped connections keep the worst-case estimate as spend.
- **Proven only against fakes so far:**
  - Fallback pricing and non-zero cache accounting. Hand-check the first real call that shows a fallback or a cache read.
  - Live attempts arrive without a `model` field, so a declined attempt may be priced at the served model.
- **Known gap until M4:** a HOLD can't be answered yet, and each repeated `ezra ask` over the limit adds another pending row.

**M3, done (2026-11-20).** Ezra intake (`intake.py`): one structured-output call routes each request as `direct`, `code` or `unsupported`. 117 tests pass and ruff is clean.
- **Code route:** writes 2–8 typed Acceptance Criteria (ids AC1… in order, at least one critical, `check` set exactly on deterministic criteria) and saves a TaskEnvelope for Code Joe with status `created`, targeting `playground/`.
- **Validation:** the schema forces the response's shape, and `problems_with()` checks the rules a schema can't express. A broken response gets one repair, which explains the problems back to the model, then fails clearly. Truncated output fails without a repair.
- **Costing:** every request gets an id up front, so the intake call is billed to the task it creates. Cost per task includes intake.
- **Caching:** the system prompt is static. The project summary (tracked files plus public signatures) and the request go in the user message, after the cached prefix.
- **CLI:** `ezra ask` prints the answer, the new task with its criteria, or the reason a request isn't supported. `ezra task <id>` shows a saved task.
- **Live checks** (back to back, on Sonnet 5.5):

  | Request | Route | Result | Cost |
  |---|---|---|---|
  | "what's 2+2" | direct | Answered | $0.0053 (wrote the 1,755-token prefix to the cache) |
  | "Add a sentence_count function to textkit…" | code | Task saved with 7 criteria: 2 critical, 4 major tests, 1 `tests_pass` | $0.0075 (read the prefix from the cache) |
  | "Email my team…" | unsupported | Explained, and offered to draft the text | $0.0016 |

  The cache read was **verified live for the first time**. The costs match hand calculations.
- **More live checks (on a throwaway database):**
  - The repair request (the rejected intake sent back as the assistant turn, then the problems) is accepted by the API, and the repaired intake passed every rule ($0.0071).
  - "make textkit better" routed to `direct` with one clarifying question instead of inventing criteria ($0.0019).
- **Robustness:**
  - The project summary handles filenames with spaces.
  - A missing or non-git project doesn't crash: questions are still answered, and a code request fails clearly without saving a task.
  - An empty reply fails instead of being replayed.
- **Caching break-even, to review in Phase 2:**
  - A cold call pays an extra 1,755 × ($2.50 − $2.00) per million tokens, about $0.0009, to write the cache.
  - Each warm call saves 1,755 × ($2.00 − $0.10) per million, about $0.0033.
  - So caching pays off once more than about 1 in 5 asks follows another within 5 minutes. Check that against real usage.
- **Leftover:** `task_43299c6a98c1` (sentence_count) is a real `created` task in the local database. M4 can use it as its first task.
- **Watch in M4/M5:** intake makes judgment calls on edge cases the user never specified. For example, "Wait... what?!" counts as 2 sentences, and text with no ending punctuation counts as 0. Guardian will hold Code Joe to those calls. If they turn out wrong in practice, consider a confirmation step for criteria intake inferred (D-009 Level 2 style).

**M4, done (2026-11-20).** Code Joe runs as a LangGraph graph: setup → plan (Opus) → Builder ∥ Tester (Sonnet tool loops) → sandboxed pytest + ruff → adjudicate and iterate, or package. 135 tests pass and ruff is clean.

- **Commands:**
  - `ezra run <task_id> [--task-budget X]`: X can only lower the cap.
  - `ezra approve <id> [--extend X]` and `ezra reject <id>`: these resume a paused task, even from a new process.
- **Carry-overs closed:**
  - Before packaging, every test-verified criterion must have an acceptance test named with its id. A missing one goes back to Tester by rule, with no model call.
  - pytest and ruff get the worktree's own root and `pyproject.toml` explicitly.
  - The store has one lock around every method, and the Gateway checks and reserves budget under one lock, so parallel calls can't overspend together.
  - The HOLD answer path is built.
- **Sandbox:**
  - Environment built from an allowlist (no API key, no shell profile) with a throwaway `HOME`.
  - The whole process group is killed on timeout, and no caches are written into the worktree.
  - `--continue-on-collection-errors` lets one broken test file not hide the rest.
  - Exact pytest node ids come from a reporter plugin, so Tier 1 matches the same names.
- **Tools and roles:**
  - File tools only (list, read, write), all through the M1 path guard.
  - Tester can read only `tests/`. Builder can't read or write `tests/acceptance/`.
  - Tool inputs are validated before they run.
  - A turn cut off at the length limit never runs its tools.
  - A model fallback mid-loop fails the agent run clearly.
  - The loop is capped at 14 turns, and the growing conversation is cached.
- **Pause and resume** (checked first with a free LangGraph probe):
  - A HOLD inside a step saves a pending approval with a stable id and pauses the graph.
  - On resume, LangGraph reruns that step from its start. The replayed pause returns the saved answer and the cap is raised. Repeating the same approval id is harmless.
  - Counters change only through returned state.
- **Live run 1** (`task_43299c6a98c1`, sentence_count): completed on `ezra/task_43299c6a98c1`.
  - 8/8 tests passed and all 7 criteria were met by Tier 1.
  - 8 model calls cost **$0.049** in total, intake included.
  - After the first turn each worker turn sent only 2–4 new input tokens; the rest (1,400–2,000) was read from the cache.
- **Live run 2** (`task_a2656c048f23`, char_count, cap lowered to $0.34): Builder finished in parallel while Tester paused with a HOLD. `ezra approve … --extend 1.66` from a new process resumed it.
  - Tester ran, and Builder wasn't rerun: still 3 calls.
  - 7/7 tests passed, with one approval row, approved.
  - Total cost $0.045.
- **Notes for later:**
  - Worst-case estimates (about $0.16 per Sonnet turn and $0.31 for the plan) are 30–80× the actual cost per call. That's safe but makes HOLDs trigger early under tight caps. Consider tuning `max_tokens` per operation in Phase 2.
  - On resume, the progress display repeats steps that finished before the pause.
  - Neither branch is merged. Merging is D-009 Level 1 and is the user's decision.
- **Bug found in review and fixed:**
  - In live run 2 the pause did not repeat on resume, because Builder's reservation was already released. So the approval's answer was never read: the $1.66 extension wasn't applied, and a rejection would have been ignored.
  - Steps now read the decision from the stored approval record when they start. A rejection stops the step before any model call. An extension raises only the cap the hold named, task or daily.
  - New tests cover a rejection and an approval where the pause doesn't repeat, and two workers paused and answered one at a time. 135 tests pass.
  - Run 2 proved pause and resume across processes live. The extension is proven by tests only. That HOLD was answered by Claude, back to the normal $2 cap, as part of the test.
- **Closed in M5 (D-015, approved by the user):** Builder can still write `conftest.py` or `pyproject.toml`, which can change how the frozen acceptance tests run, for example by skipping them. Options:
  - Block those files for Builder.
  - Have Guardian Tier 1 flag any change to them as a major finding.
- **Carried into M6:** a crash or Ctrl-C mid-run leaves the task in `running` with its worktree, and `ezra run` then refuses it. Add `ezra run --resume`, or a cleanup command.

**M5, done (2026-11-21).** Guardian review and REVISE. 151 tests pass and ruff is clean, including CLI tests for the PASS, ESCALATE and HOLD-then-approve output.

- **D-015, approved by the user:** Builder can't write `conftest.py` (at any depth) or the root `pyproject.toml`, `pytest.ini`, `setup.cfg` or `tox.ini`. The check is case-insensitive and follows symlinks.
- **Review step** (`guardian/tier2.py` plus a `review` node after `package`):
  - Tier 1 runs first, with no model call. If it finds a blocking problem, the verdict is decided right there (D-007 short-circuit).
  - Otherwise one Opus Tier 2 call reviews evidence only: the criteria with what Tier 1 proved, the diff, and the test results. It judges each inspection criterion with a quote, and reports findings outside the criteria, such as special-casing test inputs, a broken constraint, unrelated changes or security problems.
  - The verdict always comes from the D-002 table, never from the model.
- **REVISE** consumes the task's one correction cycle (D-004):
  - Builder gets Guardian's corrections.
  - Tester doesn't run again; the tests are frozen.
  - After that, failures go straight to Builder by rule, with no adjudication call.
  - The second review can't REVISE, so there is never a third attempt.
  - PASS sets the task to `done` (merging stays your call). ESCALATE sets it to `escalated`.
- **Tests:**
  - REVISE then PASS: Guardian catches special-casing and the fix arrives with the tests frozen.
  - REVISE then ESCALATE: an inspection criterion stays unmet (rule 8).
  - A task never fixed gets one REVISE, then ESCALATE (rule 4), with no Guardian model call because Tier 1 settled both reviews.
- **Live check** (a throwaway clone; Builder's first attempt replaced by flawed code, everything else real):
  - The flawed code left out char_count's docstring (inspection criterion AC4) and quietly changed word_count, breaking a constraint. The existing tests still passed.
  - Review 1 was REVISE (rule 7, Tier 2). It found AC4 unmet, quoting the line, and flagged `word_count_behavior_changed` as a major finding. It gave two concrete corrections.
  - The real Builder fixed both. Review 2 was PASS (rule 9).
  - 9 model calls cost **$0.066**. The second Guardian call read its 1,260-token instructions from the cache.
  - This is the case Guardian exists for: every test passed, and only a reviewer reading the diff against the constraints could see the problem.
- **How the live check was set up:** a throwaway clone, a hand-written task envelope (no intake), and an injected first Builder attempt. Guardian caught the missing docstring and the broken constraint **live**. Special-casing detection and both ESCALATE paths are proven with fakes only.
- **Carried into M6:**
  - The two M4 tasks (`task_43299c6a98c1`, `task_a2656c048f23`) finished at `in_review` under the old graph, before review existed, and `ezra run` only accepts `created` tasks. Add a review-only command (for example `ezra review <task>`) so they get a Guardian verdict. Don't edit the database by hand.
  - Together with M4's crash note, this argues for one "resume or re-review a stuck task" command.
- **Notes for Phase 2:**
  - A REVISE that Builder can't act on uses up the one correction cycle and two Builder runs before the inevitable ESCALATE. Example: a missing or wrong acceptance test, since the tests are frozen. Consider escalating at once when every unmet item is a test problem.
  - The model sets `auto_fixable`. A minor Tier 2 finding marked "needs user input" would escalate otherwise passing work through rule 2. Ignoring `auto_fixable` on minor findings would change a Guardian rule, so it needs the user's yes.

- **Review pass after M5 (2026-11-21), requested by the user. 158 tests pass.**
  - **Added D-016:** a call that would pass a budget cap is first shrunk to fit. Ezra HOLDs only when it can't fit.
  - **Fixed:** `ezra task` now shows Guardian's verdicts.
  - **Fixed:** the plan's cost-limit text now describes the fit step.
  - **New tests:**
    - the fit behavior: shrink, lower effort, the floors, and the daily cap
    - Guardian answers are filtered to the criteria it was asked about (re-judged, invented and duplicate entries are dropped)
    - CLI output for `run` and `task`
  - **Noted, not changed:** if Guardian's own call fails (cut off, refused or an API error), the task ends `failed` rather than `escalated`. Treating "couldn't review" as ESCALATE would match D-002's "unverifiable counts as unmet" better. It's a Guardian rule change, so it needs the user's yes.
