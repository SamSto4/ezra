import type { CSSProperties } from "react";
import { AGENT, type AgentId } from "../agents";
import { usd, type Status, type SystemInfo } from "../api";
import { Eyebrow, Meter, Panel } from "../components/bits";
import { modelName } from "../humanize";

const JOB: Record<string, string> = {
  "ezra.intake": "Reads your request", "code_joe.plan": "Plans the change",
  "code_joe.adjudicate": "Judges failed checks", "builder.implement": "Writes the code",
  "tester.write_tests": "Writes the tests", "guardian.tier2": "Reviews the work",
  "learner.reflect": "Distills lessons",
};

// How Ezra is set up right now, read-only. Changing any of this is a D-009 Level 1 decision,
// so the page shows where each value lives instead of offering edit controls.
export function SystemView({ system, status }: { system: SystemInfo | null; status: Status | null }) {
  if (!system) return <div className="panel skeleton" aria-busy="true" aria-label="Loading system" />;
  const l = system.limits;
  const verdictClass: Record<string, string> = { PASS: "ok", REVISE: "warn", HOLD: "warn", ESCALATE: "bad" };

  return (
    <>
      <div className="page-head">
        <div>
          <Eyebrow>How Ezra is set up</Eyebrow>
          <h1 className="page-title">Settings &amp; info</h1>
          <p className="page-sub">The limits and rules your agents work within. Ezra never changes these on its own:
            they live in the project's config, and any change is yours to make.</p>
        </div>
      </div>

      <Panel title="Spending" style={{ marginBottom: 16 }}>
        {status && (
          <Meter value={status.spent_today_usd} max={l.daily_budget_usd}
                 label={<span className="cost-big">{usd(status.spent_today_usd, 2)}</span>}
                 right={<span className="muted small">spent today, of {usd(l.daily_budget_usd, 0)} a day</span>} />
        )}
        <p className="dim" style={{ marginTop: 14 }}>
          Each task can spend up to <b>{usd(l.task_budget_usd, 0)}</b>, and all tasks together up to <b>{usd(l.daily_budget_usd, 0)}</b> a day.
          If a step would go over, Ezra first trims it to fit, and only asks you when it can't.
          Caching has saved <b>{usd(system.cache_saved_usd, 2)}</b> so far.
        </p>
      </Panel>

      <Panel title="Which model each agent uses" body={false}>
        <table className="table">
          <thead><tr><th>Agent</th><th>Job</th><th>Model</th><th>Thinking effort</th><th className="r hide-sm">Price per million tokens (in / out)</th></tr></thead>
          <tbody>
            {system.routing.map((r) => {
              const a = r.agent ? AGENT[r.agent as AgentId] : null;
              const p = system.prices[r.model];
              return (
                <tr key={r.operation}>
                  <td style={{ fontWeight: 600 }}>{a?.short ?? "—"}</td>
                  <td className="dim">{JOB[r.operation] ?? r.operation}</td>
                  <td>{modelName(r.model)}</td>
                  <td className="dim">{r.effort.charAt(0).toUpperCase() + r.effort.slice(1)}</td>
                  <td className="r hide-sm num dim">{p ? `$${p.input} / $${p.output}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>

      <div className="sys-grid">
        <Panel title="How Guardian decides" body={false}
               right={<span className="muted small">Checked top to bottom</span>}>
          <table className="table">
            <tbody>
              {system.verdict_rules.map((r) => (
                <tr key={r.rule} className="rule-row">
                  <td><span className={`badge ${verdictClass[r.verdict] ?? ""}`}>{r.verdict}</span></td>
                  <td className="small dim">{r.when}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="How many tries agents get">
          <ul className="plain-list">
            <li>Up to <b>{l.internal_iteration_cap}</b> rounds of fixing failed tests before Guardian sees the work.</li>
            <li>Guardian can send work back <b>{l.correction_cycle_limit === 1 ? "once" : `${l.correction_cycle_limit} times`}</b>; after that, Builder gets <b>{l.internal_iteration_cap_after_revise}</b> more round of fixes.</li>
            <li>A failed connection to Claude is retried up to <b>{l.max_infra_retries}</b> times.</li>
            <li>Tests have <b>{l.test_timeout_seconds} seconds</b> to finish.</li>
          </ul>
        </Panel>
      </div>

      <Panel title="Decisions you've made" style={{ marginTop: 16 } as CSSProperties} body={false}>
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
