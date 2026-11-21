// Turns Ezra's technical records into plain, friendly language for people.

/** "claude-opus-5-5" -> "Opus 5.5" */
export function modelName(id: string | undefined | null): string {
  if (!id) return "";
  const m = id.replace(/^claude-/, "").match(/^([a-z]+)-(\d+)(?:-(\d+))?/);
  if (!m) return id;
  return `${m[1].charAt(0).toUpperCase()}${m[1].slice(1)} ${m[2]}${m[3] ? `.${m[3]}` : ""}`;
}

const words = (s: string) => s.replace(/_/g, " ");

/** Code-ish text to readable words: drops signatures, paths and arrows. */
export function plain(s: string): string {
  return s
    .replace(/`/g, "")
    .replace(/\(([^()]*)\)\s*->\s*[\w[\]|.]+(\[[^\]]*\])?/g, "")  // f(a: int) -> int
    .replace(/(\b[a-z_]+)\(([^()]*)\)/g, "$1")              // f(a, b)
    .replace(/\b([\w-]+)\/[\w-]+\.py\b/g, "$1")             // textkit/stats.py -> textkit
    .replace(/\b(\w+)\.(\w+)\b(?!\s*\d)/g, (m, a, b) => (/^\d/.test(b) ? m : `${a}`))
    .replace(/\b[a-z]+(?:_[a-z0-9]+)+\b/g, (m) => words(m))
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** A readable task name: the intake title, cleaned up, or the first words of the goal. */
export function taskName(title: string | null | undefined, description: string): string {
  const base = title?.trim() || description.split(/[.!?]\s/)[0];
  let t = plain(base).replace(/\s+function\b/i, "").replace(/\bto textkit\b/i, "to textkit");
  if (t.length > 64) t = t.slice(0, 61).replace(/\s+\S*$/, "") + "…";
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** One line on what's going on, for under the name. */
export function taskSummary(description: string, status: string, verdict: string | null): string {
  const state: Record<string, string> = {
    created: "Ready to run", running: "Agents are working on it", in_review: "Waiting for Guardian",
    held: "Paused: waiting for your budget decision", done: verdict === "PASS" ? "Passed review" : "Finished",
    escalated: "Needs your attention", failed: "Stopped",
  };
  const sentences = description.split(/(?<=[.!?])\s/);
  // The first sentence usually starts by repeating the name ("Add X to textkit that…");
  // keep what it says the thing does.
  let goal = plain(sentences[0])
    .replace(/^(add|create|write|implement|build)\s+(an?\s+)?[\w -]+?\s+(function\s+)?(to|in)\s+\w+\s*/i, "")
    .replace(/^[,;:\s]+/, "")
    .replace(/^(that|which)\s+/i, "")
    .replace(/^returning\b/i, "returns");
  if (goal.length < 12) goal = plain(sentences.slice(1, 2).join(" ") || sentences[0]);
  goal = goal.charAt(0).toUpperCase() + goal.slice(1);
  const shortGoal = goal.length > 110 ? goal.slice(0, 107).replace(/\s+\S*$/, "") + "…" : goal;
  return `${state[status] ?? status} · ${shortGoal}`;
}

export const IMPORTANCE: Record<string, string> = {
  critical: "Must have", major: "Important", minor: "Nice to have",
};

export const OPERATION_LABEL: Record<string, string> = {
  "ezra.intake": "Ezra read your request",
  "code_joe.plan": "Code Joe planned the change",
  "code_joe.adjudicate": "Code Joe looked into a failed check",
  "builder.implement": "Builder worked on the code",
  "tester.write_tests": "Tester worked on the tests",
  "guardian.tier2": "Guardian reviewed the work",
  "learner.reflect": "Learner looked back at how it went",
};

const STATUS_WORD: Record<string, string> = { met: "passed", unmet: "did not pass", cannot_verify: "could not be checked" };

/** A friendly sentence for one trace event, from its raw data. */
export function eventSentence(kind: string, d: Record<string, unknown>, fallback: string): string {
  const n = (k: string) => Number(d[k] ?? 0);
  const list = (k: string) => (Array.isArray(d[k]) ? (d[k] as unknown[]).length : 0);
  switch (kind) {
    case "intake_routed":
      return d.route === "code" ? `Turned your request into a task with ${n("criteria")} checks to meet`
        : d.route === "direct" ? "Answered you directly" : "Explained it can't do this yet";
    case "intake_invalid": return "Fixed its own answer before going on";
    case "code_joe_started": return "Set up a private copy of the project to work in";
    case "plan_ready": return `Planned ${n("steps")} step${n("steps") === 1 ? "" : "s"} and agreed the interface`;
    case "builder_done": return `Finished the code, changing ${list("files")} file${list("files") === 1 ? "" : "s"}`;
    case "tester_done": return "Finished writing the acceptance tests";
    case "checks_ran":
      return d.passed ? `All ${n("cases")} tests passed and the code is tidy`
        : `Some tests failed (${list("failed")} of ${n("cases")})`;
    case "adjudicated":
      return d.fault === "code" ? "Decided the code needs fixing" : d.fault === "tests" ? "Decided the tests need fixing"
        : "Decided both the code and tests need fixing";
    case "packaged": return "Saved the work on its own branch";
    case "reviewed": return d.verdict === "PASS" ? "Approved the work" : d.verdict === "REVISE"
      ? "Sent the work back with fixes to make" : `Flagged it for you (${String(d.verdict).toLowerCase()})`;
    case "revision_started": return "Started on Guardian's fixes";
    case "delivered": return "Done. Ready for you to merge";
    case "escalated": return "Handed it to you to decide";
    case "code_joe_stopped": return "Stopped before finishing";
    case "budget_hold": return "Paused to ask you about the budget";
    case "budget_fit": return "Trimmed a call so it stayed within budget";
    case "hold_answered": return d.approved ? "You approved more budget" : "You declined more budget";
    case "run_resumed": return "Picked up where it left off";
    case "review_requested": return "Asked Guardian to review older work";
    case "abandoned": return "Closed by you";
    case "lessons_injected": return `Shared ${list("lessons")} lesson${list("lessons") === 1 ? "" : "s"} from earlier tasks`;
    case "lessons_learned": return list("added") || list("merged")
      ? `Learned ${list("added")} new lesson${list("added") === 1 ? "" : "s"}${list("merged") ? `, refined ${list("merged")}` : ""}`
      : "Looked back, nothing new to learn";
    case "lesson_rejected": return "Threw out a lesson that didn't pass its check";
    default: return fallback;
  }
}

export function criterionStatus(s: string | undefined) {
  return s ? STATUS_WORD[s] ?? s : "not checked yet";
}

export const timeAgoShort = (ms: number) => (ms < 60_000 ? `${Math.round(ms / 1000)}s` : `${Math.round(ms / 60_000)}m`);
