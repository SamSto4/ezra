import type { CSSProperties } from "react";
import { AGENT, type AgentId } from "../agents";
import { usd, type SystemInfo } from "../api";
import { Eyebrow, Panel } from "../components/bits";

// How Ezra is set up right now, read-only. Changing any of this is a D-009 Level 1 decision,
// so the page shows where each value lives instead of offering edit controls.
export function SystemView({ system }: { system: SystemInfo | null }) {
  if (!system) return <div className="panel skeleton" aria-busy="true" aria-label="Loading system" />;
  const l = system.limits;
  const verdictClass: Record<string, string> = { PASS: "ok", REVISE: "warn", HOLD: "warn", ESCALATE: "bad" };

  return (
    <>
      <div className="page-head">
        <div>
          <Eyebrow>How Ezra is set up</Eyebrow>
          <h1 className="page-title">System</h1>
          <p className="page-sub">The rules every agent runs under. All of it lives in <span className="mono">{system.config_dir}/</span> and
            the decisions log, and changing any of it is your call (D-009 Level 1).</p>
        </div>
      </div>

      <div className="stats">
        <div className="stat"><Eyebrow>Task budget</Eyebrow><div className="stat-value">{usd(l.task_budget_usd, 2)}</div></div>
        <div className="stat"><Eyebrow>Daily budget</Eyebrow><div className="stat-value">{usd(l.daily_budget_usd, 2)}</div></div>
        <div className="stat"><Eyebrow>Fix rounds</Eyebrow><div className="stat-value">{l.internal_iteration_cap}<span className="muted" style={{ fontSize: 15 }}> before review</span></div></div>
        <div className="stat"><Eyebrow dot="var(--accent)">Saved by cache</Eyebrow><div className="stat-value">{usd(system.cache_saved_usd, 3)}</div></div>
      </div>

      <Panel title="Who runs on which model" body={false}
             right={<span className="mono muted">routing · {system.routing_version}</span>}>
        <table className="table">
          <thead><tr><th>Agent</th><th>Operation</th><th>Model</th><th>Effort</th><th className="r hide-sm">Input / output per M</th></tr></thead>
          <tbody>
            {system.routing.map((r) => {
              const a = r.agent ? AGENT[r.agent as AgentId] : null;
              const p = system.prices[r.model];
              return (
                <tr key={r.operation}>
                  <td><span className="agent-tag" data-g={a?.glyph ?? "··"}>{a?.short ?? "—"}</span></td>
                  <td className="mono">{r.operation}</td>
                  <td className="mono">{r.model.replace("claude-", "")}</td>
                  <td><span className="pill">{r.effort}</span></td>
                  <td className="mono r hide-sm">{p ? `$${p.input} / $${p.output}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>

      <div className="sys-grid">
        <Panel title="How Guardian decides" body={false}
               right={<span className="muted small">D-002 · first match wins</span>}>
          <table className="table">
            <tbody>
              {system.verdict_rules.map((r) => (
                <tr key={r.rule} className="rule-row">
                  <td className="rule-n">{r.rule}</td>
                  <td><span className={`badge ${verdictClass[r.verdict] ?? ""}`}>{r.verdict}</span></td>
                  <td className="small dim">{r.when}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Loop limits" right={<span className="muted small">D-004</span>}>
          <dl className="kpis" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
            <div><dt>Fix rounds before review</dt><dd>{l.internal_iteration_cap}</dd></div>
            <div><dt>Fix rounds after REVISE</dt><dd>{l.internal_iteration_cap_after_revise}</dd></div>
            <div><dt>Correction cycles per task</dt><dd>{l.correction_cycle_limit}</dd></div>
            <div><dt>Retries per call</dt><dd>{l.max_infra_retries}</dd></div>
            <div><dt>Test timeout</dt><dd>{l.test_timeout_seconds}s</dd></div>
            <div><dt>Budget fit</dt><dd style={{ fontSize: 14 }}>shrink, then HOLD</dd></div>
          </dl>
          <p className="muted small" style={{ marginTop: 12 }}>A call that would pass a budget first shrinks its output limit to fit (D-016). Ezra only
            pauses with a HOLD when it can't fit.</p>
        </Panel>
      </div>

      <Panel title="Decisions" style={{ marginTop: 16 } as CSSProperties} body={false}
             right={<span className="mono muted">docs/decisions.md</span>}>
        <table className="table">
          <tbody>
            {system.decisions.map((d) => (
              <tr key={d.id}>
                <td className="mono" style={{ width: 70 }}>{d.id}</td>
                <td>{d.title}</td>
                <td className="r"><span className={`badge ${d.status === "Accepted" ? "ok" : ""}`}>{d.status.toUpperCase()}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </>
  );
}
