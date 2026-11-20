# Ezra UI plan

**Status:** accepted (D-011, 2026-11-20). Nothing gets built until Phase 1 is finished.
**Reference design:** the user's mockup, kept locally in `docs/ui/private/` (not published: it contains personal details). Keep its look: dark navy, glass cards, the four-point star mark and serif headings. Swap its content for what Ezra actually does.

---

## 1. When to build it

| When | What | Why then |
|------|------|----------|
| **Phase 1 (now, M2–M6)** | No UI. Three small design rules only (section 4) | The agent loop doesn't exist yet. A UI built now would only display fake data. |
| **Start of Phase 2: UI v1** | Home, live Agent Activity, task result card, trace viewer, approvals inbox, spend meter | Phase 2 means reading 20–50 real traces to find failures. A visual trace viewer makes that work much faster. It's the first point where the UI pays for itself. |
| **Phase 3** | Knowledge → Standards library | Standards only exist from Phase 3. |
| **Phase 4** | Knowledge → Learner profile, Automations → daily report schedule, Daily digest | Learner only exists from Phase 4. |
| **Phase 5** | Your Tools panel (Artifact Creator MCP namespaces) | Tools only exist from Phase 5. |
| **Phase 6** | Agents → model routing and eval results | The router only exists from Phase 6. |

Rule: **a panel appears only when the department behind it exists.** Empty panels and placeholder "tools" look finished, but they hide what Ezra can really do.

## 2. Mapping the mockup to Ezra

| Mockup element | Ezra version | Data source |
|---|---|---|
| "Good evening" + **Ask Ezra anything** | Same. Text goes to Ezra intake (M3). | `ezra.intake` |
| Quick actions: Research / Plan / Automate / Analyze | Replace with real routes: **Build** (Code Joe), **Ask** (direct answer). Add **Create** (Artifact Creator) and **Daily report** (Learner) in their own phases. | routing |
| "Ezra is thinking…" + response card | **Task card:** goal, verdict badge (PASS / REVISE / HOLD / ESCALATE), criteria met/unmet, branch, cost | `guardian_reviews`, `department_results` |
| Sources / Deep Dive / Add to Project | **View trace**, **Open diff**, **Approve merge** (that last one is a D-009 Level 1 action) | `events`, git worktree |
| **Agent Activity · Live** checklist | The real pipeline as it runs: Intake → Plan → Builder ∥ Tester → tests → Guardian tier → verdict. Each step shows model, tokens and cost. | `events` (streamed) |
| Report "79% complete" bar | Step progress, plus **spend against the $2 task budget** | `model_invocations` |
| Your Tools | Phase 5 only | Artifact Creator |
| Active Projects | Tasks and their `ezra/<task_id>` branches, with status | `tasks` |
| Sidebar: Agents | **Departments:** Code Joe, Guardian, Learner, Artifact Creator, each with health and review-trust level | per department |
| Sidebar: Knowledge | Standards (Phase 3) and Learner profile (Phase 4) | — |
| Sidebar: Automations | Learner's daily run (Phase 4) | — |
| Sidebar: Settings | Limits and routing are **view only**. Changing them is Level 1 under D-009, so an edit becomes an approval request. | `config/` |
| "Online · Ready to help" | Gateway status plus **today's spend against the $10 daily limit** | `model_invocations` |

### Missing from the mockup but needed

1. **Approvals inbox.** This is the most important screen. Every Level 1 HOLD (merge, push, over-budget, unresolved ESCALATE) waits here with Approve / Reject, and the answers are written to `approval_records`. Without it, a paused task stays invisible.
2. **Spend meter.** Cost per successful task is Ezra's core metric, so it should always be on screen.
3. **Trace viewer.** Shows every step, model, token count, cost and verdict for a task. It's the web version of `ezra trace` (M6).
4. **Daily digest** (Level 3 items), from Phase 4.

## 3. Proposed stack

- **Local API:** FastAPI on `127.0.0.1` only, reading the same SQLite store. Live activity comes over Server-Sent Events.
- **Frontend:** React + Vite, served locally. Optionally wrapped later as a desktop app.
- **No new logic in the UI.** The CLI and the UI are both thin clients over the same core functions.
- **No accounts and no auth** while it's bound to localhost. If it ever has to be reachable from the phone, that's the point to revisit the database and hosting (see the D-011 note in `decisions.md`).

## 4. Rules that apply during Phase 1 (cheap now, expensive later)

1. **The CLI is a thin client.** `ezra ask` / `ezra run` call functions in a core module. The CLI holds no logic of its own, so the UI can call the same functions later.
2. **Every graph step writes start and finish events** with department, step, model, status and cost. The live Activity panel then becomes a query, not a rewrite.
3. **A HOLD is a stored, pending approval record**, not just a terminal prompt. Any client can then answer it: CLI now, UI later.
