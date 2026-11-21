# Ezra: handoff context for the next agent

This file brings a new agent up to speed on everything done so far. Read it first, then `docs/decisions.md` and `docs/phase-1-plan.md`.
*Written 2026-11-21, updated after M6. It has no secrets or personal details.*

---

## 1. What Ezra is, and who it's for

- **Ezra** is the user's personal AI agent, a local Python app.
- **Architecture:** Ezra is the central orchestrator with four departments:
  - **Code Joe** (a LangGraph coding department with **Builder** and **Tester** sub-agents)
  - **Learner** (a daily workflow, Phase 4)
  - **Artifact Creator** (MCP-based, Phase 5)
  - **Guardian** (an independent reviewer)
- **Source spec:** the Google Doc "A.I. Agent execution". `docs/decisions.md` overrides it wherever they differ.
- **The user's goal is to learn** how agents work: orchestration, delegation, LangGraph state, model selection, token efficiency, memory. Explain the *why* behind design choices in plain language. The user liked visual diagrams. Token efficiency is a core value, and **cost per successful task** is the headline metric.
- **The user wants publishable research** (CV or GitHub): controlled experiments with a baseline. See §6.

## 2. How the user wants to work (follow this)

- **Communication:**
  - Plain language, with short summaries and a recap at the end.
  - Explain what changed and why; be concise when asked.
- **Commits and pushes:**
  - Commit only when asked. Pushing is a **separate yes**, every time.
  - Before any push, scan the outgoing diff for personal info. The repo is **public**.
- **Always `git fetch` before committing or pushing.** GitHub changes outside this chat: two commits (`d552421`, `ef38740`) arrived from elsewhere, and both had to be rebased over. If decision numbers clash, keep GitHub's numbers and renumber the local ones.
- **Privacy:**
  - No personal names, photos or personal email in the repo. History was rewritten once to remove them.
  - Commits use the GitHub no-reply email `277616627+SamSto4@users.noreply.github.com`. It's set in this repo's local git config.
  - The UI mockup has personal details and lives only in the gitignored `docs/ui/private/`.
- **D-009 Level 1: always ask first** before:
  - push or merge
  - changes to Guardian rules, the rubric, the path guard, loop limits, or the D-009 matrix itself
  - new providers
  - spend over $2 per task or $10 per day
- **Before substantive work, check the request shape live, cheaply.** For example, run a sub-cent probe of a new API feature, or a free LangGraph probe, before building on it.
- **State the expected cost before live runs.** Runs so far cost about $0.05–0.07 per coding task.

## 3. Environment and commands

- **Repo:** the local `Ezra A.I.` folder, on `main`. Public at https://github.com/SamSto4/ezra. Check `git log` and `git status` for what's pushed.
- **Python 3.14** with `.venv` (`.venv/bin/python`, `.venv/bin/ezra`). Main packages: `anthropic` 2.11, `langgraph` 1.2.24, `langgraph-checkpoint-sqlite` 3.1.3, `pydantic` 2.14.
- **API key:** stored in `~/.zshrc` as `ANTHROPIC_API_KEY`. The agent's Bash shell may not have it, so run live commands as `zsh -ic '.venv/bin/ezra …'`. Never print the key.
- **Tests:** `.venv/bin/python -m pytest` gives **185 passed** (about 28s). Lint: `.venv/bin/ruff check .` is clean. Tests never touch the network; they use fake clients in `tests/fakes.py`.
- **Runtime data:** `.ezra/` (gitignored) holds `ezra.db` (SQLite), `checkpoints.db` (LangGraph state) and `worktrees/`.
- **`playground/`:** a separate git repo, gitignored, containing a tiny `textkit` package. It's Code Joe's practice target.
- **CLI:**
  - `ezra ask "…"`: intake. It answers a question, creates a coding task, or says the request isn't supported.
  - `ezra task <id>`: shows a task, its spend, its Guardian reviews and its events.
  - `ezra run <task_id> [--task-budget X]`: runs Code Joe and Guardian. `X` can only *lower* the cap.
  - `ezra approve <approval_id> [--extend X]` and `ezra reject <approval_id>`: answer a budget HOLD and resume the task, even from a new process.
  - `ezra approvals`: lists pending HOLDs.
  - `ezra trace <id> [-v] [--text <hash>]`: the full timeline, with models, tokens, cost, verdicts and (with `-v`) prompt versions and injected context. Free to read.
  - `ezra run <id> --resume` / `ezra abandon <id>`: continue a cut-off task, or close a stuck one (it keeps the branch).
  - `ezra review <id>`: Guardian review for a task packaged before review existed.

## 4. Decisions (full text in `docs/decisions.md`)

| ID | Gist |
|---|---|
| D-001 | "Benchmark" is split into **Standards, Acceptance Criteria, Quality Rubric, Model Evals** |
| D-002 | Verdicts PASS, REVISE, HOLD, ESCALATE. A 9-row table, first match wins. `cannot_verify` counts as unmet. Major findings count like unmet major criteria |
| D-003 | Gate-based grading: FAIL, CONDITIONAL, PASS, EXCELLENT |
| D-004 | Three counters: infra retries ≤2 per call; internal iterations ≤2 before submission and ≤1 after REVISE; **1 correction cycle per task** |
| D-005 | The Creator sub-agent is renamed **Builder** |
| D-006 | Ezra approves autonomously |
| D-007 | Risk-tiered Guardian: Tier 0 none, Tier 1 deterministic, Tier 2 checklist, Tier 3 full rubric. Deterministic checks run first and short-circuit |
| D-008 | Build order: thin slice → traces → standards (phases 1–6) |
| D-009 | A 4-level matrix of decisions that come back to the user. Level 1 means ask first (see §2) |
| D-010 | Local Python, Claude-only, CLI, SQLite. Learner logs only interactions with Ezra |
| D-011 | **UI v1 at the start of Phase 2**. The CLI is a thin client over `core.py`. Every step writes events. HOLDs are stored approvals. The plan is in `docs/ui/ui-plan.md` |
| D-012 | Learning goals: (1) a **router experiment** (all-Opus vs static table vs dynamic router); (2) observable, versioned memory and pattern charts; (3) **progressive learning with a controlled experiment** (see §6) |
| D-013 | *(from GitHub)* Standard format and storage. Only user-stated Standards before Phase 3. Files are in `standards/` |
| D-014 | *(from GitHub)* Quality Rubric v1 in `config/rubric.yaml`, versioned, for Tier 3 |
| D-015 | Builder can't write `conftest.py` (at any depth) or the root `pyproject.toml`, `pytest.ini`, `setup.cfg` or `tox.ini` |
| D-016 | Budget fit: before a HOLD, shrink the call's `max_tokens` to fit, and lower effort one step if it falls below half. HOLD only if it can't fit (under 25% of the request or under 1,024 tokens). **Never switch models to fit** |

## 5. What's built (Phase 1, milestones M1–M6 done)

Details and live results are in `docs/phase-1-plan.md` §9.

- **M1, the foundation:**
  - Pydantic contracts with `extra=forbid` (`contracts.py`).
  - The SQLite store (`store.py`): thread-safe, and every method is locked.
  - The D-002 verdict table (`guardian/verdict.py`), the rubric (`guardian/rubric.py`, replaced by GitHub's v1) and Tier 1 (`guardian/tier1.py`).
  - Per-task git worktrees and a role-based path guard (`code_joe/workspace.py`): case-insensitive, symlink-safe, blocks `.git`; Builder is blocked from `tests/acceptance/` and test config.
- **M2, the Gateway** (`gateway.py`), the single path to Claude:
  - Routing from `config/routing.yaml`: Sonnet 5.5 for intake, Builder and Tester; Opus 5.5 for planning, adjudication and Guardian Tier 2.
  - Adaptive thinking, effort, system-prompt caching, and `fallbacks:"default"` under beta `server-side-fallback-2026-07-01`. Calls are streamed.
  - Budget: worst case = counted input tokens × the priciest cache-write rate + `max_tokens` × the priciest output rate, across the model and its fallbacks. It's checked and reserved under a lock, then fitted (D-016) or held.
  - Logging: one `ModelInvocation` row per call, plus start and finish events. Prices live in `config/pricing.yaml` and `pricing.py`. Rejected calls book $0.
- **M3, intake** (`intake.py`):
  - One structured-output call routes `direct`, `code` or `unsupported`.
  - A code request gets 2–8 typed Acceptance Criteria and a saved `TaskEnvelope`.
  - Broken answers get one repair. The system prompt is static and cached.
- **M4, the Code Joe graph** (`code_joe/graph.py`, `agents.py`, `tools.py`, `sandbox.py`):
  - The steps: setup, plan (Opus, with an interface spec), Builder and Tester in parallel (Sonnet tool loops), sandboxed pytest and ruff, then adjudicate (at most 2 rounds) or package.
  - Builder and Tester get file tools only. Tester can read only `tests/`. Inputs are validated, and cut-off turns are never run. The loop is capped at 14 turns, and the growing conversation is cached.
  - Sandbox: allowlisted environment, throwaway `HOME`, process-group kill on timeout, and exact test node ids via a reporter plugin.
  - HOLD: a pending approval with a stable id, then a LangGraph `interrupt`, saved by the SQLite checkpointer. A resumed step reruns from its start and **reads the decision from the stored approval record**.
- **M5, Guardian:**
  - `review` runs after `package`: Tier 1 first; if it hasn't decided, Tier 2, one Opus call on evidence only (`guardian/tier2.py`).
  - REVISE: Builder gets Guardian's corrections, the tests are frozen, and the second review can't REVISE. So it's PASS (done) or ESCALATE, never a third attempt.
- **Live results:**
  - Two M4 tasks completed for about $0.05 each.
  - A real parallel HOLD was approved from a new process and resumed.
  - M5's flawed-output test went REVISE then PASS for $0.066. Guardian caught a missing docstring and a quietly changed word_count, even though every test had passed.

- **M6:** trace viewer (`trace.py`), per-call attribution (prompt version, labelled context, and full texts in a local `texts` table), run leases plus resume and abandon, and `ezra review`. A real Ctrl-C found a resume bug: parallel steps that finished but weren't committed leave `next` empty. It's fixed (`core._resumable`). Both stranded tasks were reviewed and got PASS. **Baseline: about $0.075 per successful task.** Details are in `docs/phase-1-plan.md` §9.

## 6. Research and the planned experiment

`docs/research/progressive-learning.md` holds the notes and plan, with sources.
- **Frontier methods:** Reflexion, ExpeL, ReasoningBank, Dynamic Cheatsheet, Generative Agents, MemGPT, Voyager, AWM, **ACE** (itemized playbook, delta updates, no full rewrites), **GEPA**, the Anthropic memory tool, and accumulated behavioral rules.
- **The key caution:** Hajimiri et al., EMNLP 2026, found that **budget-matched** plain agents matched memory methods. Variance matters.
- **Ezra's plan, "lessons":**
  - a Reflector reads Guardian outcomes
  - Guardian validates the proposed lessons
  - a deterministic Curator applies the edits
  - retrieval is capped at about 600–800 tokens and cached, with attribution per lesson
  - Learner owns it in Phase 4
- **The experiment:** arms are control, lessons, **budget-matched control**, and optionally naive memory.
  - About 60 tasks: 40 to learn from and 20 held out, split by category.
  - **Hidden tests** are the primary metric.
  - At least 3 runs per arm, with confidence intervals, pre-registered.
  - About $30–70. Needs the user's yes.
- **No code yet.** Attribution logging is in place since M6.

## 7. Open items and carry-overs

- **D-017 (waiting on the user):** the user wants fixable REVISE findings rerun until they meet the standards, and important ones (critical, or needing the user's input) escalated to them. The proposed cap is 3 correction cycles. This changes loop limits and Guardian verdict rows (D-002), so it needs an explicit yes on both the number and the rule change.
- **Unmerged branches (all Guardian PASS):** in `playground/`: `ezra/task_43299c6a98c1` (sentence_count), `ezra/task_a2656c048f23` (char_count, with a minor ruff import-order note), `ezra/task_2449616ff1c8` (top_words) and `ezra/task_6e70fb3a99e9` (longest_word). Merging is the user's call.
- **Awaiting the user's yes (Guardian rule changes):**
  - If Guardian's own call fails, the task currently ends `failed`. Should it ESCALATE instead?
  - The model sets `auto_fixable` on findings, so a minor finding marked "needs user input" can escalate otherwise passing work (rule 2).
  - A REVISE that Builder can't act on (a test problem, since tests are frozen) wastes the correction cycle. Should Ezra escalate at once?
- **Phase 2 tuning:** worst-case estimates are 30–80× the actual cost per call. D-016 softens that. Consider per-operation `max_tokens` from real data. Caching break-even: about 1 in 5 asks must follow another within 5 minutes.
- **The user's questions on the research:** do lessons transfer across projects; the experiment budget cap; whether the router and learning experiments share a task set.

## 8. Gotchas the next agent should know

- **Pause and resume:**
  - LangGraph's `interrupt` works by raising an exception. Never wrap step code in `except Exception`; catch only Ezra's own error types.
  - A resumed step reruns from its first line. A pause may *not* happen again on that rerun, which is why decisions are read from the stored approval.
- **Claude API:**
  - Opus 5.5 and Sonnet 5.5 reject `thinking: disabled` and forced `tool_choice`; steer with the prompt instead.
  - Structured output via `output_config.format` adds about 400 input tokens for the schema.
- **Tests:**
  - Builder and Tester run in parallel threads, so test fakes must answer **per role** (`ScriptedClient`, keyed by system prompt), not from one shared queue.
  - The fake client stores message lists by reference, so read the tool-results message by index, not with `[-1]`.
- **Deterministic HOLD tests** need token counts large enough that D-016 can't shrink the call to fit (see `_plan_hold` in `tests/test_code_joe.py`).
- **A memory file** for this project exists in the previous agent's memory directory. Its facts are repeated here.
