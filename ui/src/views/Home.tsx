import { useEffect, useRef, useState } from "react";
import type { AgentId } from "../agents";
import { api, usd, type AgentInfo, type AskResult, type EzraEvent, type TaskSummary } from "../api";
import { Eyebrow, Panel, Star } from "../components/bits";
import { Orbit } from "../components/Orbit";
import { busyAgents } from "./AgentsView";

interface Turn { request: string; result?: AskResult; error?: string; started?: boolean }

/** A tiny trend line of cost per passed task, oldest to newest. */
function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const max = Math.max(...values), min = Math.min(...values), w = 160, h = 28;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (w - 4) + 2,
    h - 3 - ((v - min) / (max - min || 1)) * (h - 6)]);
  const last = pts[pts.length - 1];
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img"
         aria-label={`Cost per passed task, oldest to newest: ${values.map((v) => `$${v.toFixed(3)}`).join(", ")}`}>
      <path d={pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ")} />
      <circle cx={last[0]} cy={last[1]} r="2.5" />
    </svg>
  );
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

// Real routes only (D-011: a panel appears only when the department behind it exists).
const QUICK = [
  { label: "Build something", sub: "Code Joe plans it, Builder and Tester make it, Guardian checks it.",
    seed: "Add a function to textkit that " },
  { label: "Ask a question", sub: "A direct answer from Ezra. No task, no code.", seed: "" },
];

export function Home({ tasks, onChange, tick, events, cacheSaved }: {
  tasks: TaskSummary[]; onChange: () => void; tick: number; events: EzraEvent[]; cacheSaved: number | null;
}) {
  const [agents, setAgents] = useState<AgentInfo[] | null>(null);
  useEffect(() => { api.agents().then(setAgents).catch(() => setAgents([])); }, [tick]);
  const working = busyAgents(events);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);

  // ⌘K / Ctrl+K focuses the ask bar from anywhere on the page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); input.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [turns]);
  // Grow the textarea with its content.
  useEffect(() => {
    const el = input.current; if (!el) return;
    el.style.height = "";
    if (text.includes("\n") || el.scrollHeight > el.clientHeight + 2) el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);

  const update = (i: number, patch: Partial<Turn>) =>
    setTurns((t) => t.map((x, j) => (j === i ? { ...x, ...patch } : x)));

  async function send() {
    const request = text.trim();
    if (!request || busy) return;
    const i = turns.length;
    setBusy(true); setText("");
    setTurns((t) => [...t, { request }]);
    try { update(i, { result: await api.ask(request) }); onChange(); }
    catch (e) { update(i, { error: String(e).replace(/^Error: /, "") }); }
    finally { setBusy(false); }
  }
  async function run(i: number, taskId: string) {
    try { await api.run(taskId); update(i, { started: true }); onChange(); }
    catch (e) { update(i, { error: String(e).replace(/^Error: /, "") }); }
  }

  const passed = tasks.filter((t) => t.verdict === "PASS");
  const perTask = passed.length ? passed.reduce((n, t) => n + t.spend_usd, 0) / passed.length : null;
  const series = [...passed].reverse().map((t) => t.spend_usd); // oldest first
  const pick = (id: AgentId) => {
    window.location.hash = "/agents";
    setTimeout(() => document.getElementById(`agent-${id === "checks" ? "tester" : id}`)
      ?.scrollIntoView({ block: "start" }), 300);
  };

  return (
    <>
      <div className="hero">
        <div>
          <Eyebrow>Ezra · your agent lab</Eyebrow>
          <h1 className="hello">{greeting()}<em>.</em></h1>
          <p className="page-sub" style={{ fontSize: 16 }}>Tell Ezra what to build or ask it anything. Watch each
            agent work, see what it cost, and learn why it decided what it did.</p>
          <div className="metric-strip">
            <div className="metric">
              <Eyebrow dot="var(--accent)">Per successful task</Eyebrow>
              <div className="stat-value lime" style={{ marginTop: 10 }}>{usd(perTask, 3)}</div>
              <Spark values={series} />
            </div>
            <div className="metric">
              <Eyebrow dot="var(--success)">Passed</Eyebrow>
              <div className="stat-value" style={{ marginTop: 10 }}>{passed.length}<span className="muted" style={{ fontSize: 16 }}> / {tasks.length}</span></div>
            </div>
            <div className="metric">
              <Eyebrow>Saved by cache</Eyebrow>
              <div className="stat-value" style={{ marginTop: 10 }}>{usd(cacheSaved, 3)}</div>
            </div>
          </div>
        </div>
      </div>
      <Panel eyebrow={<Eyebrow dot={working.size ? "var(--accent)" : "var(--muted)"}>
               Ezra and its agents{working.size ? " · live" : ""}</Eyebrow>}
             right={<a className="small dim" href="#/agents">Open roster →</a>} flat style={{ marginTop: 24 }}>
        <Orbit agents={agents} busy={working} onPick={pick} />
      </Panel>

      {!turns.length && (
        <div className="quick">
          {QUICK.map((q) => (
            <button key={q.label} className="quick-card" onClick={() => { setText(q.seed); input.current?.focus(); }}>
              <strong>{q.label}</strong>
              <span className="muted small">{q.sub}</span>
            </button>
          ))}
        </div>
      )}

      <div className="conversation">
        {turns.map((t, i) => (
          <div key={i} className="fresh" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="bubble-user">{t.request}</div>
            <div className="reply">
              <Star size={24} />
              <div style={{ minWidth: 0 }}>
                {!t.result && !t.error && <div className="thinking"><i />Ezra is reading your request…</div>}
                {t.error && <p className="error">{t.error}</p>}
                {t.result?.route === "direct" && <p className="answer">{t.result.answer}</p>}
                {t.result?.route === "unsupported" && (
                  <p className="answer">Ezra can't do this yet: {t.result.unsupported_reason}</p>
                )}
                {t.result?.route === "code" && t.result.task && (
                  <Panel eyebrow={<Eyebrow dot="var(--a-intake)">New task · {t.result.task.acceptance_criteria.length} criteria</Eyebrow>}
                         title={t.result.title} flat>
                    <p className="dim">{t.result.task.description}</p>
                    <ul className="criteria compact" style={{ margin: "12px 0" }}>
                      {t.result.task.acceptance_criteria.map((c) => (
                        <li key={c.id}>
                          <span className="mono muted">{c.id}</span>
                          <span className={`sev ${c.severity}`}>{c.severity}</span>
                          <span>{c.text}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="actions">
                      {t.started
                        ? <a className="btn primary" href={`#/task/${t.result.task.task_id}`}>Watch the agents →</a>
                        : <button className="btn primary" onClick={() => run(i, t.result!.task!.task_id)}>Run with Code Joe</button>}
                      <a className="btn ghost" href={`#/task/${t.result.task.task_id}`}>Open task</a>
                    </div>
                  </Panel>
                )}
                {t.result && <p className="mono muted" style={{ marginTop: 8 }}>intake · {usd(t.result.cost_usd)}</p>}
              </div>
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>

      <form className="ask" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <label htmlFor="ask" className="sr-only">Ask Ezra</label>
        <textarea id="ask" ref={input} value={text} rows={1} placeholder="Ask Ezra anything, or describe a change…"
                  enterKeyHint="send"
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        <span className="kbd" aria-hidden>⌘K</span>
        <button className="send" type="submit" disabled={busy || !text.trim()} aria-label={busy ? "Sending" : "Send"}>
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2.2"
                  strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </form>
    </>
  );
}
