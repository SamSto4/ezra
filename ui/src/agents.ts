// One identity per agent, used everywhere (pipeline, trace, activity, roster), so the
// same color always means the same agent.

export type AgentId = "intake" | "code_joe" | "builder" | "tester" | "checks" | "guardian" | "learner";

// Volt keeps color for meaning, so agents are told apart by a two-letter monogram, not a
// rainbow. The only lit color is lime, and it always means "working right now".
export const AGENT: Record<AgentId, { name: string; short: string; glyph: string; hue: string;
                                      model: boolean; does: string }> = {
  intake: { name: "Ezra intake", short: "Intake", glyph: "EZ", hue: "var(--ink-muted)", model: true,
            does: "Routes your request and writes acceptance criteria" },
  code_joe: { name: "Code Joe", short: "Code Joe", glyph: "CJ", hue: "var(--ink-muted)", model: true,
              does: "Plans the interface, judges failed checks" },
  builder: { name: "Builder", short: "Builder", glyph: "BU", hue: "var(--ink-muted)", model: true,
             does: "Writes the code in its own worktree" },
  tester: { name: "Tester", short: "Tester", glyph: "TE", hue: "var(--ink-muted)", model: true,
            does: "Writes acceptance tests, blind to the code" },
  checks: { name: "Sandbox checks", short: "Checks", glyph: "CK", hue: "var(--ink-muted)", model: false,
            does: "Runs pytest and ruff, no model" },
  guardian: { name: "Guardian", short: "Guardian", glyph: "GU", hue: "var(--ink-muted)", model: true,
              does: "Reviews the diff and decides the verdict" },
  learner: { name: "Learner", short: "Learner", glyph: "LE", hue: "var(--ink-muted)", model: true,
             does: "Turns finished tasks into lessons for next time" },
};

/** Trace step (from the server) → the agent that owns it. */
export function agentOfStep(step: string): AgentId | null {
  switch (step) {
    case "intake": return "intake";
    case "setup": case "plan": case "adjudicate": case "package": return "code_joe";
    case "builder": case "revise": return "builder";
    case "tester": return "tester";
    case "checks": return "checks";
    case "review": case "deliver": case "escalate": return "guardian";
    case "learner": return "learner";
    default: return null;
  }
}

/** Model operation → agent. */
export function agentOfOperation(op: string): AgentId | null {
  if (op.startsWith("ezra.")) return "intake";
  if (op.startsWith("code_joe.")) return "code_joe";
  if (op.startsWith("builder.")) return "builder";
  if (op.startsWith("tester.")) return "tester";
  if (op.startsWith("guardian.")) return "guardian";
  if (op.startsWith("learner.")) return "learner";
  return null;
}

/** The pipeline, in order. Builder and Tester run side by side. */
export const PIPELINE: { id: AgentId; label: string; steps: string[] }[][] = [
  [{ id: "intake", label: "Route & criteria", steps: ["intake"] }],
  [{ id: "code_joe", label: "Plan", steps: ["setup", "plan"] }],
  [
    { id: "builder", label: "Build", steps: ["builder", "revise"] },
    { id: "tester", label: "Write tests", steps: ["tester"] },
  ],
  [{ id: "checks", label: "pytest + ruff", steps: ["checks"] }],
  [{ id: "code_joe", label: "Adjudicate", steps: ["adjudicate"] }],
  [{ id: "guardian", label: "Review", steps: ["review", "deliver", "escalate"] }],
];
