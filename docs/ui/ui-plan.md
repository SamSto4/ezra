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

---

## 5. Progress

**M7, UI v1, done (2026-11-21).** Phase 2 starts here. 190 tests pass, ruff is clean, and the UI builds with strict TypeScript.

- **Local API** (`src/ezra/api.py`, FastAPI): a thin layer over `ezra.core`, like the CLI.
  - Reads: status (today's spend, limits, pending approvals, running jobs), tasks, a task with its full trace, stored texts, approvals, events, and a live **Server-Sent Events** stream.
  - Actions: ask, run, resume, review, abandon, and answering a HOLD. Long actions run in a background thread; the UI follows them on the event stream.
  - **Safety:** it listens on 127.0.0.1 only and refuses any Host that isn't localhost, which blocks DNS rebinding. Every write needs an `X-Ezra-Client` header, which other websites can't send without a CORS preflight, and this server allows no cross-origin requests. So a web page can't start tasks or approve spend.
- **Web UI** (`ui/`, React and Vite, no other dependencies), in the mockup's look: dark navy, glass cards, the star mark and serif headings. The greeting has no personal name.
  - **Home:** "Ask Ezra anything". A code request shows its acceptance criteria and a **Run with Code Joe** button.
  - **Agent Activity (live):** each pipeline step as it happens, the model calls in flight, and spend.
  - **Task page:** status and verdict, criteria ticked by Guardian's results, cost against the $2 budget with a per-operation bar chart, Guardian reviews (findings and corrections), and the **visual trace**. Click a call to see its prompt version and injected context, and open any stored text or reply. Buttons offer run, resume, review and abandon where they apply.
  - **Tasks:** every task, plus the **cost per successful task**.
  - **Approvals inbox:** HOLDs with Approve and Reject; answering one resumes the task.
  - **Sidebar:** online status and today's spend against $10.
  - Panels for Learner, Standards, Tools and the router stay out until those departments exist (section 1).
- **Run it:** `cd ui && npm install && npm run build` once, then `ezra ui` and open http://127.0.0.1:8765. For UI development, `npm run dev` on :5173 forwards `/api` to `ezra ui`.
- **Live check:** a request typed into the UI (`unique_words`, task `task_679a17c0987c`) went through intake, then **Run with Code Joe**. The activity panel followed every step live, and the task ended **PASS** for **$0.075**, which matches the baseline.
- **Proven with tests only:** the approvals inbox answering a real HOLD. The API test covers a HOLD, then a rejection from the inbox, then the task stopping.

**Agent-focused redesign (2026-11-21, design-engineer pass).** The look is still the mockup's (D-011).
- **One color per agent, everywhere:** Intake blue, Code Joe violet, Builder green, Tester cyan, sandbox checks grey, Guardian amber. The same hue marks an agent in the pipeline, the trace, the live activity and the roster.
- **Agents page** (`#/agents`, backed by `/api/agents` and `src/ezra/roster.py`):
  - A flow diagram of how a coding request moves through the agents. An agent glows while it has a model call in flight.
  - One card per agent: its role, model and effort per operation, current prompt version, calls, cost, cost per call, share of input read from cache, average time, and tasks.
  - Each card also shows what the agent can and can't touch, and one agent-specific number. Guardian's is a verdict bar plus how many reviews Tier 1 settled for free.
- **Task page:** a clickable **agent pipeline** (Intake → Plan → Build ∥ Write tests → pytest + ruff → Adjudicate → Review).
  - Each node shows its state (done, working, failed, waiting or not needed) with its calls and cost.
  - Clicking a node filters the trace to that agent's steps.
  - Cost bars use the agent colors.
- **Live activity:** names which agent is working right now, on which model.
- **Checks run in the browser** (the skill's Python checker needs Playwright, which isn't installed here):
  - No contrast failures on any page, and no horizontal overflow at 375, 768 or 1440 px.
  - Every target is at least 24 px, the focus ring is visible, and reduced-motion and reduced-transparency fallbacks exist.
  - On phones the sidebar becomes a top bar and the flow stacks vertically.

**UI v2 (2026-11-21):** redesigned from Awwwards references. The direction, sources and rules are in [awwwards-brief.md](awwwards-brief.md).
