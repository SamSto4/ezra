import { useEffect, useState } from "react";
import { AGENT, agentOfOperation, type AgentId } from "../agents";
import { api, usd, type AgentInfo, type BoardRow, type EzraEvent } from "../api";
import { ago, Eyebrow, Panel } from "../components/bits";
import { Orbit } from "../components/Orbit";
import { eventSentence, modelName, taskName } from "../humanize";

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

const ORDER: AgentId[] = ["intake", "code_joe", "builder", "tester", "checks", "guardian", "learner"];
const STATE: Record<string, { word: string; cls: string }> = {
  working: { word: "Working on it", cls: "live" },
  done: { word: "Done its part", cls: "met" },
  needs_attention: { word: "Hit a problem", cls: "unmet" },
  waiting: { word: "Up next", cls: "pending" },
  not_needed: { word: "Not needed", cls: "quiet" },
};

// The agents workspace: pick an agent, see where it stands on every task, and step in.
export function AgentsView({ tick, events, onChange }: { tick: number; events: EzraEvent[]; onChange: () => void }) {
  const [agents, setAgents] = useState<AgentInfo[] | null>(null);
  const [board, setBoard] = useState<Record<string, BoardRow[]> | null>(null);
  const [error, setError] = useState("");
  const [pick, setPick] = useState<AgentId>("builder");
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    api.agents().then(setAgents).catch((e) => setError(String(e)));
    api.board().then(setBoard).catch((e) => setError(String(e)));
  }, [tick]);

  const busy = busyAgents(events);
  const info = agents?.find((a) => a.id === pick);
  const spec = AGENT[pick];
  const rows = board?.[pick] ?? [];
  const active = rows.filter((r) => r.state !== "not_needed");
  const shown = showAll ? rows : active.slice(0, 12);
  const working = ORDER.flatMap((a) => (board?.[a] ?? []).filter((r) => r.state === "working").map((r) => ({ a, r })));
  const models = (a?: AgentInfo) => (a ? [...new Set(a.operations.map((o) => modelName(o.model)))].join(" + ") : "");

  async function act(fn: () => Promise<unknown>) {
    try { await fn(); onChange(); } catch (e) { setError(String(e).replace(/^Error: /, "")); }
  }

  return (
    <div className="workspace">
      <div className="page-head">
        <div>
          <Eyebrow dot={working.length || busy.size ? "var(--accent)" : "var(--muted)"}>
            {working.length || busy.size ? "Someone's working" : "Everyone's free"}
          </Eyebrow>
          <h1 className="page-title">Your agents</h1>
          <p className="page-sub">Pick an agent to see where it stands on each task, and step in when it needs you.</p>
        </div>
        <a className="btn primary" href="#/home">Give Ezra something to do</a>
      </div>
      {error && <p className="error" style={{ marginBottom: 12 }}>{error}</p>}

      {!!working.length && (
        <div className="now-strip" role="status">
          {working.map(({ a, r }) => (
            <a key={`${a}${r.task_id}`} href={`#/task/${r.task_id}`} className="now-item">
              <span className="pad-dot live-dot" aria-hidden /> <b>{AGENT[a].short}</b> is working on {taskName(r.title, r.description)}
            </a>
          ))}
        </div>
      )}

      <div className="ws-grid">
        <Panel flat title="Team" body={false} className="ws-picker">
          <Orbit agents={agents} busy={busy} selected={pick} onPick={(id) => setPick(id)} compact />
          <ul className="agent-list" aria-label="Agents">
            {ORDER.map((id) => {
              const r = board?.[id] ?? [];
              const now = r.filter((x) => x.state === "working").length;
              const done = r.filter((x) => x.state === "done").length;
              const prob = r.filter((x) => x.state === "needs_attention").length;
              const a = agents?.find((x) => x.id === id);
              return (
                <li key={id}>
                  <button aria-pressed={pick === id} className={`agent-row ${pick === id ? "on" : ""}`}
                          onClick={() => setPick(id)}>
                    <span className={`pad-dot ${now || busy.has(id) ? "live-dot" : ""}`} aria-hidden />
                    <span className="agent-row-text">
                      <b>{AGENT[id].short}</b>
                      <span className="muted small">
                        {now ? "Working now" : prob ? `${prob} need${prob === 1 ? "s" : ""} a look` : done ? `${done} done` : "Nothing yet"}
                        {a && id !== "checks" ? ` · ${models(a)}` : ""}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </Panel>

        <div className="ws-detail">
          <Panel title={spec.name}
                 right={<span className={`status ${busy.has(pick) ? "live" : ""}`}><i />
                   {busy.has(pick) ? "Working now" : info?.last_at ? `Last active ${ago(info.last_at)}` : "Not active yet"}</span>}>
            <p className="dim">{info?.role ?? spec.does}</p>
            {info && (
              <div className="row-meta" style={{ marginTop: 12 }}>
                {pick !== "checks" && <span className="pill">{models(info)}</span>}
                <span className="muted small">Spent {usd(info.cost_usd, 2)} so far</span>
                {pick === "learner" && <span className="muted small">· Learning is {info.memory === "lessons" ? "on" : info.memory === "frozen" ? "using lessons only" : "off"} · <a href="#/lessons">See lessons</a></span>}
              </div>
            )}
            {info && (
              <details className="rights-toggle">
                <summary>What it can and can't do</summary>
                <div className="rights">
                  <div className="can"><Eyebrow dot="var(--success)">Can</Eyebrow><ul>{info.can.map((c) => <li key={c}>{c}</li>)}</ul></div>
                  <div className="cannot"><Eyebrow dot="var(--danger)">Can't</Eyebrow><ul>{info.cannot.map((c) => <li key={c}>{c}</li>)}</ul></div>
                </div>
              </details>
            )}
          </Panel>

          <Panel title={`${spec.short} on each task`} body={false} style={{ marginTop: 16 }}
                 right={rows.length > active.length || rows.length > 12
                   ? <button className="link small" onClick={() => setShowAll((v) => !v)}>{showAll ? "Only where it took part" : `Show all ${rows.length}`}</button>
                   : undefined}>
            {board === null && <p className="muted small" style={{ padding: 22 }}>Loading…</p>}
            {board !== null && !shown.length && (
              <p className="dim" style={{ padding: 22 }}>{spec.short} hasn't worked on any task yet.</p>
            )}
            <ul className="work-list">
              {shown.map((r) => {
                const st = STATE[r.state] ?? STATE.waiting;
                return (
                  <li key={r.task_id} className={`work-row ${r.state}`}>
                    <div className="work-main">
                      <a href={`#/task/${r.task_id}`} className="task-name">{taskName(r.title, r.description)}</a>
                      <span className="muted small">
                        {r.last_kind ? eventSentence(r.last_kind, r.last_data, r.last_detail ?? "") : st.word}
                        {r.model ? ` · ${modelName(r.model)}` : ""}{r.cost_usd ? ` · ${usd(r.cost_usd, 3)}` : ""}
                        {r.last_at ? ` · ${ago(r.last_at)}` : ""}
                      </span>
                    </div>
                    <span className={`result ${st.cls}`}>{st.word}</span>
                    <div className="work-actions"><Action agent={pick} row={r} act={act} /></div>
                  </li>
                );
              })}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}

/** The one useful thing you can do with this agent on this task right now, if any. */
function Action({ agent, row, act }: { agent: AgentId; row: BoardRow; act: (fn: () => Promise<unknown>) => void }) {
  const s = row.task_status;
  if (s === "held") return <a className="btn" href="#/approvals">Answer</a>;
  if (row.state === "working") return <a className="btn ghost" href={`#/task/${row.task_id}`}>Watch</a>;
  if (s === "created" && ["code_joe", "builder", "tester"].includes(agent))
    return <button className="btn" onClick={() => act(() => api.run(row.task_id))}>Start it</button>;
  if (agent === "guardian" && s === "in_review" && !row.verdict)
    return <button className="btn" onClick={() => act(() => api.review(row.task_id))}>Review now</button>;
  if (agent === "learner" && ["done", "escalated"].includes(s) && row.state !== "done")
    return <button className="btn" onClick={() => act(() => api.learn(row.task_id))}>Learn from it</button>;
  if (["running", "in_review"].includes(s) && row.state === "waiting")
    return <button className="btn ghost" onClick={() => act(() => api.resume(row.task_id))}>Pick up</button>;
  return <a className="btn ghost" href={`#/task/${row.task_id}`}>Open</a>;
}
