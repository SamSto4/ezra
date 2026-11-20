# How agents build long-term memory and learn patterns

A learning guide for Ezra (D-012). Each section explains a concept, then shows where it lives in Ezra and when you'll be able to watch it happen.

---

## 1. The model forgets everything

A Claude call is **stateless**. It knows only what's in that one request: the instructions, the conversation so far and anything we paste in. When the call ends, nothing is kept.

So an agent's "memory" is never inside the model. It's a **system around the model** that does three things:

1. **Saves** something worth remembering.
2. **Finds** it again later.
3. **Puts it back** into a future prompt.

Everything below is a variation on that loop. It also explains the trade-off: every remembered fact you re-inject costs input tokens on every call that carries it.

## 2. Four kinds of memory

| Kind | What it holds | Lifespan | In Ezra |
|------|---------------|----------|---------|
| **Working memory** | The current context window: this task's prompt, files, recent turns | One call or one task | The `messages` the Gateway sends |
| **Episodic memory** | What happened: events, decisions, outcomes, with timestamps | Permanent, append-only | `events`, `model_invocations`, `guardian_reviews` in SQLite (built in M1–M2) |
| **Semantic memory** | Distilled facts: "the user prefers short answers", "this repo uses pytest" | Long-lived, versioned, can be corrected | User profile and project facts (Learner, Phase 4) |
| **Procedural memory** | How to do things: rules, checklists, prompts that work | Long-lived, versioned | **Standards** (Phase 3), prompts, routing policy |

The key idea: **episodic memory is raw, and the others are distilled from it.** You don't remember every conversation; you remember what they taught you. Agents work the same way.

## 3. The memory pipeline

```
capture → distill → validate → store (versioned) → retrieve → inject → measure
   ↑                                                                    │
   └──────────────────────── feedback ──────────────────────────────────┘
```

| Step | What it means | Ezra's version |
|------|---------------|----------------|
| **Capture** | Record what happened, in full | Every model call and step writes events (D-011 rule) |
| **Distill** | Turn many episodes into a few statements | Learner's daily run reads the day's events and proposes facts or Standards |
| **Validate** | Don't trust a memory just because a model wrote it | Guardian reviews Learner's proposals. Each one is marked **explicit** (you said it) or **inferred** (Ezra guessed it). |
| **Store** | Save it with version, source and date | Every entry links back to the tasks or events it came from (provenance) |
| **Retrieve** | Pick only the memories relevant to *this* task | By scope (global, department, project), then relevance |
| **Inject** | Put them in the prompt | Stable memories go in the cached part of the prompt, so re-sending them is cheap |
| **Measure** | Did the memory help? | Compare pass rate and cost per task before and after it was activated |

**Why validation and provenance matter:**
- A wrong memory is worse than none, because it gets re-injected into every future task.
- **Memory poisoning** means bad information gets saved and then trusted forever. The usual defense is to always know where a memory came from, who approved it, and how to undo it.
- That's why D-009 makes an *inferred* Standard a Level 2 decision: Ezra activates it but tells you right away, with a one-step rollback.

## 4. How memory changes over time

Memories aren't written once. They go through a lifecycle:

- **Created**: first seen, low confidence
- **Reinforced**: seen again in later tasks, so confidence rises
- **Corrected**: you or Guardian contradict it, so a new version replaces the old
- **Decayed**: not used or confirmed for a long time, so it's flagged for review
- **Retired**: removed, but kept in history

To **see pattern changes**, memory has to be versioned like code. Every change is a new version with a date and a reason, so you can diff "what Ezra believed in March" against "what it believes now." That's the plan for Ezra's Knowledge panel (D-011, Phases 3–4): a **memory timeline**, where each entry shows its history and the tasks that taught it.

## 5. Finding patterns

A pattern is something that repeats across many episodes. Agents find patterns in three places.

**In failures (Phase 2: error analysis)**
- Read 20–50 traces and tag why each one failed: misunderstood the request, wrong file, weak tests, and so on.
- Count the tags. The biggest category is what to fix first.
- That count is the **failure taxonomy** in D-008.

**In corrections (Phase 3: Standards from evidence)**
- If Guardian keeps REVISE-ing for the same reason, that reason should become a Standard.
- Builder then gets it right the first time, which saves a correction cycle and its tokens.

**In you (Phase 4: Learner)**
- Repeated preferences, recurring requests, and the times of day you work.
- Learner proposes these as facts. Explicit ones are applied, and inferred ones go through validation.

**How to see patterns change, as charts:**
- **Cost per successful task** over time. This is Ezra's core metric.
- **First-try PASS rate**: how often the work passes without a REVISE.
- **REVISE reasons by category**, week by week. A category that shrinks after a Standard is added shows the memory worked.
- **Token mix**: input against output, cached against uncached. Rising cache reads mean the memory is being re-used cheaply.

Every one of these is a query over tables Ezra already writes.

## 6. Prompting as memory

A prompt is procedural memory written in plain language. Treat prompts like code:

- **Version them.** Every prompt change gets an ID, so a trace shows which prompt version produced it.
- **Test them.** A prompt change is judged against a fixed set of tasks (Model Evals, Phase 6), not by how it feels.
- **Keep the stable part first.** Caching is a prefix match, so stable instructions and memories go at the top and the task-specific content at the bottom. A changing date or ID near the top breaks the cache and multiplies cost.
- **Shorter is often better.** Every remembered line is paid for on every call. Good memory systems prune.

## 7. What you'll be able to watch, by phase

| When | What becomes visible |
|------|----------------------|
| **Now (M2)** | Every model call: model, tokens, cache reads, cost (`ezra ask` footer and the database) |
| **M6** | `ezra trace <task_id>`: a whole task's episode, step by step |
| **Phase 2** | Failure taxonomy; UI v1 with the live trace viewer |
| **Phase 3** | Standards with versions and history: procedural memory you can diff |
| **Phase 4** | Learner's daily report, user profile, memory timeline: semantic memory and how it changes |
| **Phase 6** | Router experiment (D-012): how much routing saves, measured |

## 8. Glossary

- **Context window**: everything the model can see in one call.
- **Episodic, semantic and procedural memory**: what happened, what's true, and how to do it.
- **Distillation**: compressing many episodes into a few reusable statements.
- **Provenance**: where a memory came from (which tasks, who approved it).
- **Retrieval**: choosing which memories to include in a prompt.
- **Prompt caching**: reusing an unchanged prompt prefix at about a twentieth of the input price on Ezra's models.
- **Memory poisoning**: a wrong memory that gets saved and trusted.
- **Drift**: behavior slowly changing as memories and prompts change. You catch it by measuring over time.
