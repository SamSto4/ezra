import { useEffect, useRef, useState } from "react";
import { api, usd, type AskResult, type EzraEvent, type TaskSummary } from "../api";
import { Eyebrow, Panel, Star } from "../components/bits";
import { taskName, taskSummary } from "../humanize";
import { busyAgents } from "./AgentsView";

interface Turn { request: string; result?: AskResult; error?: string; started?: boolean }

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

export function Home({ tasks, onChange, events }: {
  tasks: TaskSummary[]; onChange: () => void; tick: number; events: EzraEvent[]; cacheSaved: number | null;
}) {
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


  return (
    <>
      <div className="hero">
        <Eyebrow>Ezra</Eyebrow>
        <h1 className="hello">{greeting()}<em>.</em></h1>
        <p className="page-sub" style={{ fontSize: 16 }}>What should your agents work on? Ask below, or pick up where they left off.</p>
      </div>

      {!turns.length && <Inbox tasks={tasks} onChange={onChange} working={working.size > 0} />}

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


/** What needs you, what's ready to start, and what's in progress: things you can act on. */
function Inbox({ tasks, onChange, working }: { tasks: TaskSummary[]; onChange: () => void; working: boolean }) {
  const needs = tasks.filter((t) => t.status === "held" || t.status === "escalated");
  const ready = tasks.filter((t) => t.status === "created");
  const going = tasks.filter((t) => t.status === "running" || t.status === "in_review");
  const [err, setErr] = useState("");
  async function start(id: string) {
    try { await api.run(id); onChange(); } catch (e) { setErr(String(e).replace(/^Error: /, "")); }
  }
  const row = (t: TaskSummary, action: React.ReactNode) => (
    <li key={t.task_id} className="inbox-row">
      <a href={`#/task/${t.task_id}`} className="inbox-text">
        <span className="task-name">{taskName(t.title, t.description)}</span>
        <span className="task-sub">{taskSummary(t.description, t.status, t.verdict)}</span>
      </a>
      {action}
    </li>
  );
  return (
    <div className="inbox">
      {err && <p className="error">{err}</p>}
      {!!needs.length && (
        <Panel title="Needs you" body={false} eyebrow={<Eyebrow dot="var(--warn)">{needs.length} waiting</Eyebrow>}>
          <ul className="inbox-list">{needs.map((t) => row(t, t.status === "held"
            ? <a className="btn primary" href="#/approvals">Answer</a>
            : <a className="btn" href={`#/task/${t.task_id}`}>Take a look</a>))}</ul>
        </Panel>
      )}
      {!!ready.length && (
        <Panel title="Ready to start" body={false}>
          <ul className="inbox-list">{ready.map((t) => row(t, <button className="btn primary" onClick={() => start(t.task_id)}>Start</button>))}</ul>
        </Panel>
      )}
      {!!going.length && (
        <Panel title="In progress" body={false} eyebrow={working ? <Eyebrow dot="var(--accent)">Agents are working</Eyebrow> : undefined}>
          <ul className="inbox-list">{going.map((t) => row(t, <a className="btn ghost" href={`#/task/${t.task_id}`}>Watch</a>))}</ul>
        </Panel>
      )}
      {!needs.length && !ready.length && !going.length && (
        <Panel>
          <p className="dim">Nothing needs you, and nobody's busy. Ask for something below to get your agents going.</p>
        </Panel>
      )}
    </div>
  );
}
