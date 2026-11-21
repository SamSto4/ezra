import { useEffect, useState, type CSSProperties } from "react";
import { AGENT, agentOfOperation, type AgentId } from "../agents";
import { api, usd, type AgentInfo, type EzraEvent } from "../api";
import { ago, Eyebrow, Panel } from "../components/bits";
import { modelName } from "../humanize";

const JOB: Record<string, string> = {
  "ezra.intake": "Reads your request", "code_joe.plan": "Plans the change",
  "code_joe.adjudicate": "Judges failed checks", "builder.implement": "Writes the code",
  "tester.write_tests": "Writes the tests", "guardian.tier2": "Reviews the work",
  "learner.reflect": "Distills lessons",
};
import { Orbit } from "../components/Orbit";

/** Agents with a model call in flight right now, from the live event stream. */
export function busyAgents(events: EzraEvent[]): Set<AgentId> {
  const open = new Map<string, number>();
  for (const e of events) {
    const op = String(e.data.operation ?? "");
    if (e.kind === "model_call_started") open.set(op, (open.get(op) ?? 0) + 1);
    if (e.kind === "model_call_finished") open.set(op, Math.max(0, (open.get(op) ?? 0) - 1));
  }
  const busy = new Set<AgentId>();
  open.forEach((n, op) => { const a = agentOfOperation(op); if (n > 0 && a) busy.add(a); });
  return busy;
}

const VERDICT_ORDER = ["PASS", "REVISE", "HOLD", "ESCALATE"];

export function AgentsView({ tick, events }: { tick: number; events: EzraEvent[] }) {
  const [agents, setAgents] = useState<AgentInfo[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.agents().then((a) => { setAgents(a); setError(""); }).catch((e) => setError(String(e)));
  }, [tick]);
  const busy = busyAgents(events);
  const jump = (id: string) => document.getElementById(`agent-${id}`)?.scrollIntoView({ block: "start" });

  return (
    <>
      <div className="page-head">
        <div>
          <Eyebrow>Meet the team</Eyebrow>
          <h1 className="page-title">Agents</h1>
          <p className="page-sub">Each agent has one job, its own model, and clear limits on what it can touch.</p>
        </div>
      </div>
      {error && <p className="error">{error}</p>}

      <Panel eyebrow={<Eyebrow dot={busy.size ? "var(--accent)" : "var(--muted)"}>
               Ezra and its agents{busy.size ? " · live" : ""}</Eyebrow>} flat>
        <Orbit agents={agents} busy={busy} onPick={(id) => jump(id === "checks" ? "tester" : id)} />
        <p className="muted small" style={{ marginTop: 12 }}>
          Ezra routes each request, then Code Joe plans it, Builder and Tester work side by side, the sandbox
          runs the checks, and Guardian decides. If checks fail, Code Joe judges whether the code or the tests are
          wrong (up to 2 rounds). If Guardian says REVISE, Builder fixes it once with the tests frozen.
        </p>
      </Panel>

      {!agents && !error && (
        <div className="agent-grid">{[0, 1, 2, 3].map((i) => <div key={i} className="panel skeleton" aria-hidden />)}</div>
      )}
      {agents && (
        <div className="agent-grid">
          {agents.map((a) => {
            const id = a.id as AgentId;
            const live = busy.has(id);
            const latency = a.operations.reduce((n, o) => n + o.latency_ms, 0);
            return (
              <section key={a.id} id={`agent-${a.id}`} className={`panel agent ${live ? "live" : ""}`}
                       style={{ "--hue": AGENT[id].hue } as CSSProperties}>
                <header className="panel-head">
                  <h3 className="agent-name">{a.name}</h3>
                  <span className={`status ${live ? "live" : ""}`}><i />
                    {live ? "Working now" : a.last_at ? `Active ${ago(a.last_at)}` : "Not run yet"}</span>
                </header>
                <div className="panel-body">
                  <p className="agent-role">{a.role}</p>
                  <div className="ops">
                    {a.operations.map((o) => (
                      <div key={o.operation} className="op">
                        <span className="clip">{JOB[o.operation] ?? o.operation}</span>
                        <span className="pill">{modelName(o.model)}</span>
                        <span className="muted small">{o.effort.charAt(0).toUpperCase() + o.effort.slice(1)} effort</span>
                      </div>
                    ))}
                  </div>
                  <dl className="kpis">
                    <div><dt>Spent so far</dt><dd>{usd(a.cost_usd, 2)}</dd></div>
                    <div><dt>Reused from cache</dt><dd>{Math.round(a.cache_share * 100)}%</dd></div>
                    <div><dt>Usual time per step</dt><dd>{a.calls ? `${(latency / a.calls / 1000).toFixed(1)}s` : "—"}</dd></div>
                  </dl>
                  <AgentSpecific a={a} />
                  <div className="rights">
                    <div className="can"><Eyebrow dot="var(--ok)">Can</Eyebrow><ul>{a.can.map((c) => <li key={c}>{c}</li>)}</ul></div>
                    <div className="cannot"><Eyebrow dot="var(--bad)">Can't</Eyebrow><ul>{a.cannot.map((c) => <li key={c}>{c}</li>)}</ul></div>
                  </div>
                </div>
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}

function AgentSpecific({ a }: { a: AgentInfo }) {
  if (a.id === "guardian") {
    const v = a.verdicts ?? {};
    const total = Object.values(v).reduce((n, x) => n + x, 0);
    if (!total) return <p className="agent-fact small">No reviews yet.</p>;
    return (
      <>
        <div className="verdict-bar" role="img" aria-label={VERDICT_ORDER.map((k) => `${k} ${v[k] ?? 0}`).join(", ")}>
          {VERDICT_ORDER.filter((k) => v[k]).map((k) => <span key={k} className={`seg v-${k}`} style={{ flexGrow: v[k] }} />)}
        </div>
        <p className="small dim">
          {VERDICT_ORDER.filter((k) => v[k]).map((k) => `${v[k]} ${k === "PASS" ? "approved" : k.toLowerCase()}`).join(" · ")}
          <span className="muted"> · {a.tier1_only ?? 0} decided by automatic checks alone</span>
        </p>
      </>
    );
  }
  const facts: Record<string, string> = {
    intake: `Has read ${a.routed ?? 0} of your requests.`,
    code_joe: `Has planned ${a.plans ?? 0} tasks${a.adjudications ? ` and untangled ${a.adjudications} failed checks` : ""}.`,
    builder: `Has built ${a.runs ?? 0} changes${a.revisions ? `, ${a.revisions} after Guardian's notes` : ""}.`,
    tester: `Has written tests for ${a.runs ?? 0} tasks, without ever seeing the code.`,
    learner: a.memory === "off"
      ? `Learning is switched off right now, so it's resting. ${a.lessons_active ?? 0} lessons on file.`
      : `Knows ${a.lessons_active ?? 0} lessons, learned from ${a.learned_from ?? 0} tasks.`,
  };
  return <p className="agent-fact small">{facts[a.id]}</p>;
}
