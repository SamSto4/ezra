import type { CSSProperties } from "react";
import { AGENT, PIPELINE } from "../agents";
import { usd, type TraceRow } from "../api";
import { modelName } from "../humanize";

export type NodeKey = string; // `${agentId}:${label}`
type State = "waiting" | "active" | "done" | "failed" | "skipped";

interface NodeState { state: State; calls: number; cost: number; note: string; model: string }

const TERMINAL = ["done", "escalated", "failed"];

function nodeState(rows: TraceRow[], steps: string[], running: boolean, status: string,
                   isLast: boolean): NodeState {
  const mine = rows.filter((r) => steps.includes(r.step));
  const calls = mine.filter((r) => r.invocation);
  const cost = calls.reduce((n, r) => n + (r.invocation?.actual_cost_usd ?? 0), 0);
  const events = mine.filter((r) => !r.invocation);
  const note = events.length ? events[events.length - 1].detail : "";
  if (!mine.length) {
    return { state: TERMINAL.includes(status) ? "skipped" : "waiting", calls: 0, cost: 0, note: "", model: "" };
  }
  const model = modelName(calls[calls.length - 1]?.invocation?.model_id);
  if (running && isLast) return { state: "active", calls: calls.length, cost, note, model };
  const failed = mine.some((r) => /FAILED|ESCALATE|stopped/.test(r.detail));
  return { state: failed ? "failed" : "done", calls: calls.length, cost, note, model };
}

const rank: Record<State, number> = { failed: 4, active: 3, done: 2, skipped: 1, waiting: 0 };

/** The agent pipeline as one line of light: the line fills up to the furthest stop reached,
 *  and while a task runs a pulse travels along it to the agent that's working. */
export function Pipeline({ rows, running, status, selected, onSelect }: {
  rows: TraceRow[]; running: boolean; status: string;
  selected: NodeKey | null; onSelect: (k: NodeKey | null, steps: string[]) => void;
}) {
  const lastStep = rows[rows.length - 1]?.step;
  const stops = PIPELINE.map((stage) => stage.map((n) => ({
    ...n, key: `${n.id}:${n.label}`,
    st: nodeState(rows, n.steps, running, status, !!lastStep && n.steps.includes(lastStep)),
  })));
  const stopState = (i: number): State =>
    stops[i].map((n) => n.st.state).sort((a, b) => rank[b] - rank[a])[0];
  let reached = -1;
  stops.forEach((_, i) => { if (["done", "active", "failed"].includes(stopState(i))) reached = i; });
  const progress = reached <= 0 ? 0 : reached / (stops.length - 1);
  const activeIdx = stops.findIndex((_, i) => stopState(i) === "active");

  return (
    <div className="line" role="list" aria-label="Agent pipeline for this task">
      <div className="line-track" aria-hidden
           style={{ "--progress": progress } as CSSProperties}>
        <div className="line-progress" />
        {running && activeIdx > 0 && (
          <div className="line-pulse"
               style={{
                 "--from": `calc(${((activeIdx - 1) / (stops.length - 1)) * 100}cqw - 36px)`,
                 "--to": `calc(${(activeIdx / (stops.length - 1)) * 100}cqw - 36px)`,
               } as CSSProperties} />
        )}
      </div>
      {stops.map((stage, i) => (
        <div key={i} role="listitem" className={`stop ${stopState(i)}`}
             style={{ "--hue": AGENT[stage[0].id].hue } as CSSProperties}>
          <span className="node-dot" aria-hidden />
          {stage.map((n) => {
            const a = AGENT[n.id];
            return (
              <button key={n.key} type="button"
                      className={`node ${n.st.state} ${selected === n.key ? "selected" : ""}`}
                      style={{ "--hue": a.hue } as CSSProperties}
                      aria-pressed={selected === n.key}
                      title={n.st.note || undefined}
                      onClick={() => onSelect(selected === n.key ? null : n.key, n.steps)}>
                <span className="node-agent">{a.short}</span>
                <span className="node-label">{n.label}</span>
                <span className="node-meta">
                  {n.st.state === "waiting" && "Waiting"}
                  {n.st.state === "skipped" && "Not needed"}
                  {n.st.state === "active" && "Working…"}
                  {(n.st.state === "done" || n.st.state === "failed") &&
                    (a.model ? `${n.st.model} · ${usd(n.st.cost, 3)}` : "No model · free")}
                </span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
