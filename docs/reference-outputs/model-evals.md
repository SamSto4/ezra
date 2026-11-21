# Reference output: Model Evals

**Produced by:** the eval runner (Phase 6) and Guardian/Tier 1 checks that grade each case.
**Read by:** Ezra (approves a model for an operation, D-009 Level 2), the router, and the D-012
router experiment.
**Governed by:** D-001, D-012, D-014, spec routing addendum §7–8, `config/pricing.yaml`.

## What "best" means here

An eval result is evidence for a decision: *is this model good enough for this operation, and
what does a success cost?* The best result record answers both from data anyone can re-run,
and puts **cost per passing case** next to the pass rate, because that is Ezra's core metric
(cost per successful task). It reports quality as **hard gates passed**, not an averaged
score, so a cheap model can't buy its way past a correctness failure (spec §7: "A model cannot
compensate for failing a critical correctness requirement by performing well in speed or
cost").

D-014 keeps token efficiency **out** of the rubric score; it is measured here, in dollars and
tokens, from the Gateway's own logs. (The spec's illustrative 5% "token efficiency" weight is
replaced by this.)

| Property | Best output | Why it matters |
|---|---|---|
| Reproducible | Exact model id, effort, suite + prompt version, timestamp | A result you can't re-run can't approve a model |
| Gate-based | Per case: hard gates passed or not, with the failure type | Matches how tasks are actually judged (D-002/D-003) |
| Costed | Tokens split into input / cache read / output, priced from `pricing.yaml` | Cost per pass is computed, not estimated |
| Headline | Pass rate **and** cost per passing case | The two numbers the router trades off |
| Honest about spread | Runs per case and the range, once there are ≥ 3 runs (D-012) | Single runs vary |
| Compact | Numbers and codes, no narrative | It's stored for every model × operation × version |

## Same eval, two result records

Suite: `builder.implement` v1 (4 cases), candidate Sonnet 5.5 at `medium` effort.
**All values below are illustrative**, but the arithmetic is real: each `cost_usd` is the
token counts priced at Sonnet 5.5's rates in `config/pricing.yaml`.

### Weak

<!-- example: model-evals/weak -->
```json
{
  "model": "sonnet",
  "suite": "coding",
  "score": 87,
  "result": "Strong performance overall. The model handled most coding tasks well and produced clean, readable code. A few minor issues on edge cases. Recommended for production use."
}
```

What's wrong: "sonnet" isn't a model id; no suite or prompt version, so it can't be re-run;
an averaged 87 hides that one case **failed a hard gate**; no tokens or cost, so cost per
success is unknowable; "recommended for production" is a decision the record has no evidence
for (and qualification is not approval: spec §8).

### Best

<!-- example: model-evals/best -->
```json
{
  "model": "claude-sonnet-5-5",
  "effort": "medium",
  "operation": "builder.implement",
  "suite": "builder.implement@1",
  "prompt_version": "builder-system@3",
  "rubric_version": "1",
  "run_at": "2026-11-21T10:00:00Z",
  "runs_per_case": 1,
  "cases": [
    {"case": "BLD-CG-01", "hard_gates_passed": true,  "tokens": {"input": 3200, "cache_read": 1800, "output": 900},  "cost_usd": 0.01558, "failures": []},
    {"case": "BLD-CG-02", "hard_gates_passed": true,  "tokens": {"input": 3400, "cache_read": 1800, "output": 1400}, "cost_usd": 0.02098, "failures": []},
    {"case": "BLD-CG-03", "hard_gates_passed": false, "tokens": {"input": 3100, "cache_read": 1800, "output": 2100}, "cost_usd": 0.02738, "failures": ["major_criterion_unmet:AC2"]},
    {"case": "BLD-CG-04", "hard_gates_passed": true,  "tokens": {"input": 3600, "cache_read": 1800, "output": 1100}, "cost_usd": 0.01838, "failures": []}
  ],
  "summary": {
    "pass_rate": 0.75,
    "total_cost_usd": 0.08232,
    "cost_per_pass_usd": 0.02744,
    "failure_types": {"major_criterion_unmet": 1}
  },
  "status": "evaluating",
  "notes": ["1 run per case: below the 3 needed for a spread (D-012)."]
}
```

Why it's best: anyone can re-run it; the failed case and its reason are visible; cost per pass
($0.08232 ÷ 3 = $0.02744) includes the cost of the failure, which is what a failure really
costs; and the status stays `evaluating` until there are enough runs. Note that the failing
case also produced the *most* output tokens: long outputs are not a sign of quality.

## Checklist

- [ ] Exact model id, effort, suite/prompt/rubric versions, timestamp.
- [ ] Per case: gates passed, failure type, tokens split three ways, cost.
- [ ] Summary: pass rate and cost per passing case; failures counted by type.
- [ ] ≥ 3 runs per case before comparing models; report the range.
- [ ] Status follows the lifecycle (candidate → evaluating → qualified); approval is separate.

## Sources

Shared evidence for all four reference files: the best output is the shortest one that fully
meets the requirements, and quality must be judged on gates, not on length or polish.

**Longer is rated higher without being better**
- Dubois et al., *Length-Controlled AlpacaEval* (2024). Correcting for length raised agreement
  with Chatbot Arena rankings (Spearman 0.94 → 0.98). https://arxiv.org/abs/2404.04475
- Li, Angelopoulos, Chiang, *Does style matter?* (LMSYS, 2024). In Arena votes, length was the
  largest style effect (coefficient 0.249). https://lmsys.org/blog/2024-08-28-style-control/
- Zheng et al., *Judging LLM-as-a-Judge* (2023). Names verbosity and self-enhancement biases in
  LLM judges. https://arxiv.org/abs/2306.05685

**The same accuracy with far fewer tokens**
- Han et al., *Token-Budget-Aware LLM Reasoning* (2024). A token budget in the prompt cuts
  reasoning tokens with only a slight accuracy loss. https://arxiv.org/abs/2412.18547
- Xu et al., *Chain of Draft* (2025). Matches or beats chain-of-thought accuracy on its tasks
  with as little as 7.6% of the tokens (a best case). https://arxiv.org/abs/2502.18600

**Judge on checklists and evidence, and price success, not calls**
- Cook et al., *TICK* (2024). Yes/no checklists raised LLM–human agreement from 46.4% to 52.2%
  versus direct scoring. https://arxiv.org/abs/2410.03608
- Kapoor et al., *AI Agents That Matter* (2024). Agent evals should optimise accuracy and cost
  jointly. https://arxiv.org/abs/2407.01502

**Claude-specific levers**
- Anthropic, *Effort* docs. Effort affects every output token (text, tool calls, thinking);
  Opus 5.5 defaults to `medium`, Sonnet 5.5 to `high`; run an effort sweep on your own evals.
  https://platform.claude.com/docs/en/build-with-claude/effort
