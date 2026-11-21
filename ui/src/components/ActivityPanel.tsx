import type { CSSProperties } from "react";
import { AGENT, agentOfOperation, type AgentId } from "../agents";
import type { EzraEvent, TaskSummary } from "../api";
import { usd } from "../api";
import { clock, Eyebrow, StatusDot, VerdictBadge } from "./bits";

// The pipeline as it runs, one line per step, from the live event stream.
const STEP_TEXT: Record<string, (d: Record<string, unknown>) => string> = {
  intake_routed: (d) => `Routed as ${d.route}`,
  code_joe_started: () => "Worktree ready",
  plan_ready: (d) => `Planned ${d.steps} steps`,
  builder_done: (d) => `Code written in ${d.turns} turns`,
  tester_done: (d) => `Tests written in ${d.turns} turns`,
  checks_ran: (d) => (d.passed ? "Tests and lint passed" : "Checks failed"),
  adjudicated: (d) => `Judged the failure: ${d.fault}`,
  packaged: () => "Committed on its branch",
  reviewed: (d) => `Verdict ${d.verdict}`,
  revision_started: () => "Sent back to Builder",
  delivered: () => "PASS · ready for you",
  escalated: () => "ESCALATE · needs you",
  budget_hold: () => "Paused on a budget HOLD",
  hold_answered: (d) => (d.approved ? "HOLD approved" : "HOLD rejected"),
  run_resumed: () => "Resumed",
  code_joe_stopped: () => "Stopped",
};
const EVENT_AGENT: Record<string, AgentId> = {
  intake_routed: "intake", code_joe_started: "code_joe", plan_ready: "code_joe",
  adjudicated: "code_joe", packaged: "code_joe", builder_done: "builder",
  revision_started: "builder", tester_done: "tester", checks_ran: "checks",
  reviewed: "guardian", delivered: "guardian", escalated: "guardian",
};
const TERMINAL = ["delivered", "escalated", "code_joe_stopped", "budget_hold", "intake_routed"];

export function ActivityPanel({ events, tasks }: { events: EzraEvent[]; tasks: TaskSummary[] }) {
  const lastTask = [...events].reverse().find((e) => e.task_id)?.task_id;
  const mine = events.filter((e) => e.task_id === lastTask);
  const steps = mine.filter((e) => STEP_TEXT[e.kind]);
  const inflight = mine.filter((e) => e.kind === "model_call_started" && !mine.some(
    (f) => f.kind === "model_call_finished" && f.id > e.id && f.data.operation === e.data.operation));
  const last = steps[steps.length - 1];
  const running = (!!last && !TERMINAL.includes(last.kind)) || inflight.length > 0;
  const spent = mine.filter((e) => e.kind === "model_call_finished")
    .reduce((n, e) => n + Number(e.data.cost_usd ?? 0), 0);

  return (
    <>
      <section className="rail-section" aria-live="polite">
        <div className="rail-head">
          <Eyebrow dot={running ? "var(--ok)" : "var(--muted)"}>Live activity</Eyebrow>
          {lastTask && <span className="mono muted">{usd(spent)}</span>}
        </div>
        {!lastTask && <p className="muted small">Quiet. Steps appear here the moment an agent starts.</p>}
        {lastTask && (
          <>
            <a className="mono dim" href={`#/task/${lastTask}`}>{lastTask} →</a>
            <ol className="feed" style={{ marginTop: 12 }}>
              {steps.map((s) => {
                const a = EVENT_AGENT[s.kind];
                return (
                  <li key={s.id} className="fresh" style={{ "--hue": a ? AGENT[a].hue : "var(--muted)" } as CSSProperties}>
                    <div className="t"><span>{STEP_TEXT[s.kind](s.data)}</span>
                      <span className="mono muted">{clock(s.at).slice(0, 5)}</span></div>
                  </li>
                );
              })}
              {running && inflight.map((c) => {
                const a = agentOfOperation(String(c.data.operation));
                return (
                  <li key={c.id} className="now fresh" style={{ "--hue": a ? AGENT[a].hue : "var(--accent)" } as CSSProperties}>
                    <div className="t"><span>{a ? AGENT[a].name : String(c.data.operation)} is working</span>
                      <span className="mono muted">{String(c.data.model).replace("claude-", "")}</span></div>
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </section>
      <section className="rail-section">
        <div className="rail-head">
          <Eyebrow>Recent tasks</Eyebrow>
          <a className="small dim" href="#/tasks">All →</a>
        </div>
        <ul className="task-list">
          {tasks.slice(0, 6).map((t) => (
            <li key={t.task_id}>
              <a href={`#/task/${t.task_id}`}>
                <span className="clip">{t.description}</span>
                <span className="row-meta">
                  <StatusDot status={t.status} />
                  {t.verdict && <VerdictBadge verdict={t.verdict} />}
                  <span className="mono muted" style={{ marginLeft: "auto" }}>{usd(t.spend_usd, 3)}</span>
                </span>
              </a>
            </li>
          ))}
          {!tasks.length && <li className="muted small">No tasks yet.</li>}
        </ul>
      </section>
    </>
  );
}
