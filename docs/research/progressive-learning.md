# Progressive learning and pattern recognition in agents: research notes and plan

**Status:** research notes and a plan (D-012, goal 3). No code changes yet.
**Date:** 2026-11-21.
**Question:** how do frontier agents get better from their own experience without retraining the model? How should Ezra do it? And how do we *prove* it helps, against an agent that doesn't learn?

---

## 1. Summary

- The frontier has converged on **learning in context, not in weights**. An agent judges its own outcomes, distills short reusable lessons from successes *and* failures, curates them with small incremental edits, and retrieves only the relevant few into future prompts.
- The best-known methods differ mainly in **what** they store:
  - insights: ExpeL
  - strategies: ReasoningBank
  - workflows: AWM
  - code skills: Voyager
  - a whole evolving playbook: ACE
  - optimized prompts: GEPA
  - human-validated rules: accumulated behavioral rules
- **The warning sign:** a 2026 budget-matched study found that a plain agent given the *same token budget* matched or beat three memory methods (AWM, ASI, ReasoningBank) while often using fewer tokens. It also found that run-to-run variance changes conclusions. So our experiment must compare against a **budget-matched control** and report **variance**, or the result won't be credible.
- **Ezra's advantage:** most papers have to build a judge. Ezra already has one, Guardian, which gives a structured verdict, criterion-level results, finding codes and repair instructions for every task. That's an unusually clean learning signal.

## 2. How the pioneers do it

### 2.1 Learning within one task (reflection)
- **Reflexion** (Shinn et al., 2023): after a failed attempt, the agent writes a verbal self-critique and retries with it in context. This works within a task, but the lesson doesn't carry across tasks.
- **Ezra today:** Code Joe's adjudication and Guardian's REVISE already do this, with one correction cycle per task (D-004).

### 2.2 Learning across tasks (experiential memory)
- **ExpeL** (Zhao et al., AAAI 2024): gathers trajectories on training tasks, compares successes with failures, and extracts natural-language **insights** plus example successes, used at inference. It's been criticised because insights can be hallucinated generalizations.
- **ReasoningBank** (Ouyang et al., ICLR 2026; Google): judges each finished task, then distills **generalizable strategy items from both successes and failures**. It retrieves them before acting and stores new ones after.
  - Including failures helped: 46.5 → 49.7 on WebArena with Gemini-2.5-flash.
  - **MaTTS** contrasts several rollouts of the same task to produce better memories.
  - Reported caveat: memory can be contaminated by wrong self-judgments.
- **Dynamic Cheatsheet** (Suzgun et al., EACL 2026): a short, **self-curated** cheat sheet of transferable heuristics and code snippets, updated at test time. Transcripts are never stored, which keeps the context from growing out of control.
- **Generative Agents** (Park et al., 2023): an append-only **memory stream** and periodic **reflection** that synthesizes higher-level observations. Retrieval is scored by recency, importance and relevance. This is the origin of "reflection" as a memory-building step.
- **MemGPT / Letta** (Packer et al., 2023): an operating-system-style **tiered memory**, with a small in-context working set and a large external store that the agent pages in and out.

### 2.3 Procedural memory (skills and workflows)
- **Voyager** (Wang et al., 2023): stores **executable code skills** in a growing library and composes new skills from old ones.
- **Agent Workflow Memory** (Wang et al., ICML 2025): induces reusable **workflows** (a description plus steps) from past trajectories, offline or online. Workflows build on each other.
  - Reported gains: +24.6% and +51.1% relative success on Mind2Web and WebArena, with fewer steps.

### 2.4 Evolving the context or prompt itself
- **ACE, Agentic Context Engineering** (Zhang et al., ICLR 2026): treats the context as an **evolving playbook**. It splits the work into a **Generator** (does the task), a **Reflector** (extracts lessons) and a **Curator** (merges them in).
  - Two failure modes it fixes: **brevity bias** (optimizers shrink prompts into generic advice) and **context collapse** (rewriting the whole memory each time erodes detail). The fix is **itemized, incremental delta updates**: add, merge or update counters, never a full rewrite.
  - It needs no labels and learns from execution feedback.
  - Reported: +10.6% on agent tasks.
- **GEPA** (Agrawal et al., ICLR 2026 oral): evolves prompts by **reflecting in natural language on trajectories** instead of using a scalar reward, and keeps a Pareto set of candidates.
  - Reported: beats GRPO reinforcement learning by 6% on average (up to 20%) with up to 35× fewer rollouts, and beats MIPROv2 by over 10 points.
- **Anthropic memory tool and context editing:** a client-side file memory that Claude reads and writes across sessions, plus clearing of stale tool results.
  - Anthropic reports +39% for memory plus context editing, and +29% for context editing alone.
  - The design principle is **just-in-time retrieval** over loading everything up front.

### 2.5 Human-validated rules (closest to Ezra's Standards)
- **Accumulated behavioral rules** (Aggarwal & Farhady Ghalaty, 2026; arXiv 2607.13091): every *accepted* human review comment becomes a persistent rule in a version-controlled instruction file. Each session loads it, and a self-review checklist runs before review.
  - Reported: rules grew from 5 to 18 over 11 sessions, with **0% recurrence of ruled-against error classes**.
  - Caveats: one deployment and a small sample.
  - **Recurrence rate** is a metric worth borrowing.

### 2.6 Warning signs
- **Budget-matched baselines** (Hajimiri et al., EMNLP 2026; arXiv 2606.15017): a plain agent given the same token budget as the memory methods matched or beat them, often with fewer tokens. Run-to-run variance materially changed outcomes.
- **Memory contamination and hallucinated lessons:** a wrong self-judgment becomes a wrong lesson that is re-injected forever (seen in ReasoningBank and ExpeL critiques).
- **Persistent sycophancy:** a 2026 benchmark shows self-improving personal agents can *remember* agreeing with the user and keep doing it.
- **Ceiling effect:** where the base model already succeeds, there's no failure to learn from, so memory can't help.
- **Benchmarks are emerging** for this specific problem:
  - AgentMemoryBench (ICLR 2026) measures improvement, retention, forgetting, generalization and conflict.
  - EvoAgentBench, PAST-Bench and PATH-Bench are newer and only partly reviewed here.

## 3. What the pioneers have in common

1. **Learn from judged outcomes.** No judge, no learning. Self-judgment is the weak link.
2. **Distill; don't store transcripts.** Short, itemized lessons generalize. Raw trajectories bloat the context.
3. **Keep failures,** and contrast them with successes.
4. **Update incrementally.** Add, merge, update counters or retire, never rewrite (ACE).
5. **Curate:** de-duplicate, track helpful and harmful counts, retire stale or harmful items.
6. **Retrieve few and relevant,** just in time. Every injected token is paid for on every call.
7. **Provenance and validation:** know which task taught a lesson, who approved it, and how to undo it.
8. **Evaluate against a budget-matched baseline and report variance** (the 2026 lesson).

## 4. How Ezra should do it: "lessons"

Ezra can combine the strongest ideas:
- **ReasoningBank:** learn from successes and failures.
- **ACE:** an itemized playbook with delta updates.
- **Behavioral rules:** human-validated rules and recurrence tracking.

It all sits on signals Ezra *already logs*.

### 4.1 Signals Ezra already has (captured in M1–M5)
| Signal | Where | What it teaches |
|---|---|---|
| Guardian REVISE corrections and finding codes | `guardian_reviews` | What Builder gets wrong, in Guardian's words |
| Adjudication faults (code vs tests) | `events` | Whether Builder or Tester is the weak link, per task type |
| Intake repairs | `events: intake_invalid` | Which criteria-writing rules the model breaks |
| Test failures before review | `events: checks_ran` | Recurring bug classes |
| Budget fits and HOLDs | `events: budget_fit/budget_hold` | Which operations are over-provisioned |
| Your answers to escalations and HOLDs | `approval_records` | Your actual preferences, explicit and therefore trustworthy |

### 4.2 The pipeline (Learner owns it: Phase 4, with groundwork in Phases 2–3)
```
task ends → Reflector → candidate lessons → Guardian validates → Curator applies deltas → playbook
                                                                                           │
            next task: retrieve top-k lessons for this operation and project ◄─────────────┘
            after it: count helpful or harmful for each lesson that was injected
```
- **A lesson item** has these fields:
  - id
  - scope: global, department, operation or project
  - when it applies (the trigger)
  - the lesson itself, one or two sentences
  - kind: strategy, pitfall or check
  - evidence (task ids)
  - source: inferred, or confirmed by you
  - `helpful` / `harmful` counts
  - status: candidate, active or retired
  - version and dates
- **Reflector** (a cheap model, run after each task, at batch pricing where possible): reads the *structured* outcome (verdict, corrections, findings, failures), never the full transcript, and proposes zero to three lessons. It also **contrasts** a REVISE'd first attempt with its passing fix (the MaTTS idea, for free).
- **Validation** (Guardian, D-007 Tier 2):
  - reject lessons that contain task-specific literals, such as test values, because that's leakage
  - reject contradictions with active lessons or your Standards
  - reject vague advice (brevity bias)
  - an inferred lesson activates as D-009 Level 2 (do, then tell you); one you confirmed becomes a Standard
- **Curator:** deterministic code, not a model. It applies the deltas (ADD, MERGE into a near-duplicate, bump counters, RETIRE when `harmful` passes `helpful` or the lesson goes unused for N tasks). The playbook is never rewritten as a whole.
- **Retrieval:** filter by operation, department and project, then rank by helpful-minus-harmful and recency, within a **token budget** of about 600–800 tokens per call.
  - Place the lessons as a second cached system block, sorted deterministically, so they ride the prompt cache.
- **Attribution:** each injected lesson is logged on the invocation. Guardian's verdict for that task updates its counters. That gives a per-lesson *value per 1k tokens*.

### 4.3 Pattern recognition (what you'll be able to see, D-012)
- **Failure taxonomy over time:** finding codes, REVISE reasons and adjudication faults per week.
- **Recurrence rate per error class:** borrowed from the behavioral-rules paper. Once a lesson exists, does that error stop appearing?
- **Lesson timeline:** when each lesson was born, merged or retired, and its helpful/harmful history (the memory timeline in the UI, D-011).
- **Drift alarms:** a lesson whose `harmful` count rises, or PASS rate falling after a change.

### 4.4 Where it lands in the roadmap
| Phase | Addition |
|---|---|
| 2 (error analysis) | Hand-label the failure taxonomy from real traces. Build the **hidden-test harness** for the experiment (§5). |
| 3 (Standards) | Standards are lessons *you* confirmed. Same schema, `source=confirmed`. |
| 4 (Learner) | Reflector, Validator and Curator, plus retrieval and attribution. |
| 6 (evals and routing) | Run the experiment (§5), next to the router experiment (D-012). |

## 5. The experiment: does learning help, per token?

Designed to be published in the GitHub repo and cited on a CV. The standard is "a skeptical reviewer would accept it".

### 5.1 Hypotheses (pre-registered in the repo *before* running)
- **H1:** on held-out tasks, Ezra with lessons gets a higher **true success rate** (hidden tests pass) than Ezra without lessons.
- **H2:** Ezra with lessons has a lower **cost per successful task**.
- **H3:** with lessons, previously seen error classes recur less often.
- **H0 to beat:** a budget-matched Ezra without lessons does just as well (Hajimiri et al.).

### 5.2 Arms
| Arm | What's different | Why it's there |
|---|---|---|
| **A. Control** | No lessons. Everything else identical. | The baseline |
| **B. Ezra lessons** | Retrieved lessons, curated as in §4 | The treatment |
| **C. Budget-matched control** | No lessons, but the tokens B spends on lessons go to extra effort or an extra fix round instead | Separates "learning" from "just more tokens" |
| **D. Naive memory** *(optional)* | Raw summaries of recent past tasks, uncurated | Shows whether *curation* matters, not just memory |

Everything else is frozen:
- pinned model ids, routing table, prompts, limits and Guardian rules
- the same task order within a run, randomized across runs
- prompt-cache warm-up handled the same way in every arm

### 5.3 Tasks
- About **60 coding tasks** in the playground style. Categories: new functions, edge-case fixes, bug fixes, small refactors, docs. Varied difficulty, so the base model **isn't at its ceiling**.
- **Hidden tests**, written ahead of time, outside Ezra, and never shown to Ezra, decide true success. Guardian's verdict is a secondary metric, so we're not grading Ezra with its own judge.
- **Split:** about 40 tasks form the **learning stream** (lessons accumulate); about 20 are **held out** for evaluation (lessons frozen). The split is by category, so lessons can't memorize answers. A second fold swaps categories.

### 5.4 Metrics
- **Primary:** success rate on hidden tests; cost per successful task.
- **Secondary:**
  - first-try PASS rate, and REVISE and ESCALATE rates
  - tokens (input, output, cached)
  - lesson tokens injected
  - latency
  - recurrence rate per error class
  - **negative transfer** (tasks A solved that B failed)
- **Per lesson:** helpful and harmful counts, and value per 1k tokens.

### 5.5 Statistics
- Run each arm **at least 3 times**. Report mean ± standard deviation, and **95% bootstrap confidence intervals**, paired by task.
- Success: McNemar or a paired permutation test. Cost: Wilcoxon signed-rank.
- Report variance as a headline number, not a footnote.
- Publish everything, including null or negative results. A careful "it didn't help per token" is still a credible research result.

### 5.6 Threats to validity, and the guards
| Threat | Guard |
|---|---|
| Lessons leak answers | Category-split held-out set; the validator rejects literals; spot-checked by hand |
| Judge bias (Guardian grading itself) | Hidden tests are the primary metric |
| "It's just more tokens" | Arm C, budget-matched |
| Nondeterminism | At least 3 runs, report variance |
| Model updates mid-experiment | Pinned model ids; run all arms in the same window, interleaved |
| Small sample | Confidence intervals; a second fold; claims scoped to the task family |
| Sycophancy or contamination | Lessons come from Guardian outcomes and your explicit answers, never from self-praise |

### 5.7 Cost and approval
- At about $0.05–0.10 per task (measured in M4 and M5): 60 tasks × 3–4 arms × 3 runs ≈ 540–720 runs ≈ **$30–70**.
- That's over the $10/day default, so the run needs **your explicit yes and a budget** (D-009 Level 1), spread over days or under a one-time experiment budget.

### 5.8 What gets published
- `experiments/` folder in the repo:
  - the pre-registration
  - the task set, with hidden tests
  - run scripts
  - raw per-call logs, scrubbed of personal info
  - analysis notebook and charts
  - a results README
- **One headline sentence**, for example: "Curated lessons improved held-out success by X pp (95% CI …) at Y% lower cost per success than a budget-matched control." Or the honest null result.

## 6. Implications for the build (no code now)
- Keep logging structured outcomes. M1–M5 already do; keep that discipline in M6.
- In M6 or Phase 2, make sure every model call can record **which prompt version and which injected context** it used. Attribution depends on it.
- Plan a run-level setting for later (`memory: off | lessons | naive`, plus a budget-match knob) so the arms differ by configuration only, never by code paths.
- The hidden-test harness belongs in Phase 2, alongside error analysis.

## 7. Questions for you (not needed yet)
1. Should lessons stay per-project, or may they transfer across projects? That changes how much they can help, and the leakage risk.
2. Experiment budget: a one-time cap, such as $75, and whether it may run over several days.
3. Should the router experiment (D-012) and this one share the same task set? It's cheaper, but it couples their results.

---

## Sources
- Shinn et al., *Reflexion*, 2023: [arXiv 2303.11366](https://arxiv.org/abs/2303.11366)
- Zhao et al., *ExpeL: LLM Agents Are Experiential Learners*, AAAI 2024: [arXiv 2308.10144](https://arxiv.org/abs/2308.10144)
- Ouyang et al., *ReasoningBank*, ICLR 2026: [arXiv 2509.25140](https://arxiv.org/abs/2509.25140) · [Google Research blog](https://research.google/blog/reasoningbank-enabling-agents-to-learn-from-experience/)
- Suzgun et al., *Dynamic Cheatsheet*, EACL 2026: [arXiv 2504.07952](https://arxiv.org/abs/2504.07952)
- Park et al., *Generative Agents*, 2023: [arXiv 2304.03442](https://arxiv.org/abs/2304.03442)
- Packer et al., *MemGPT*, 2023: [arXiv 2310.08560](https://arxiv.org/abs/2310.08560)
- Wang et al., *Voyager*, 2023: [arXiv 2305.16291](https://arxiv.org/abs/2305.16291)
- Wang et al., *Agent Workflow Memory*, ICML 2025: [arXiv 2409.07429](https://arxiv.org/abs/2409.07429)
- Zhang et al., *Agentic Context Engineering (ACE)*, ICLR 2026: [arXiv 2510.04618](https://arxiv.org/abs/2510.04618)
- Agrawal et al., *GEPA*, ICLR 2026: [arXiv 2507.19457](https://arxiv.org/abs/2507.19457)
- Anthropic, memory tool and context management: [announcement](https://www.anthropic.com/news/context-management) · [memory tool docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- Aggarwal & Farhady Ghalaty, *Self-Improving AI Coding Agents Through Accumulated Behavioral Rules*, 2026: [arXiv 2607.13091](https://arxiv.org/abs/2607.13091)
- Hajimiri et al., *Are Online Skill and Memory Modules Always Worth Their Tokens?*, EMNLP 2026: [arXiv 2606.15017](https://arxiv.org/abs/2606.15017)
- *Self-Improvement Memory Enables Continual Recursive Self-Improvement*, 2026: [arXiv 2611.18856](https://arxiv.org/abs/2611.18856)
- *Agents Don't Just Agree, They Remember* (persistent sycophancy), 2026: [arXiv 2607.10526](https://arxiv.org/abs/2607.10526)
- *Memory in the Age of AI Agents* (survey), 2025: [arXiv 2512.13564](https://arxiv.org/abs/2512.13564)

*Notes on evidence:* the reported numbers come from each paper's abstract or the authors' own posts, gathered on 2026-11-21. They weren't re-checked against full texts. Re-check them before quoting any in a write-up.
