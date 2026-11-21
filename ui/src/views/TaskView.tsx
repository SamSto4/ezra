import { useEffect, useState, type CSSProperties } from "react";
import { AGENT, agentOfOperation, agentOfStep } from "../agents";
import { api, usd, type SystemInfo, type TaskDetail, type TraceRow } from "../api";
import { Meter, Panel, StatusDot, useFresh, VerdictBadge } from "../components/bits";
import { Pipeline, type NodeKey } from "../components/Pipeline";
import {
  eventSentence, IMPORTANCE, modelName, OPERATION_LABEL, taskName, taskSummary,
} from "../humanize";

const CONTEXT_LABEL: Record<string, string> = {
  task: "The task", criteria: "The criteria", constraints: "The constraints",
  project_files: "The project's files", plan: "The plan", interface_spec: "The interface",
  fix_feedback: "What to fix", failing_checks: "The failing checks", project_summary: "A project summary",
  request: "Your request", settled_by_tier1: "What the automatic checks found", test_results: "The test results",
  diff: "The changes",
};

export function TaskView({ id, tick, onChange, system }:
  { id: string; tick: number; onChange: () => void; system: SystemInfo | null }) {
  const [cap, setCap] = useState("");
  const [learnOn, setLearnOn] = useState(false);
  const [diff, setDiff] = useState<{ diff: string; note?: string; truncated?: boolean } | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);
  const [t, setT] = useState<TaskDetail | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [text, setText] = useState<{ title: string; body: string } | null>(null);
  const [focus, setFocus] = useState<{ key: NodeKey; steps: string[] } | null>(null);
  const fresh = useFresh();

  useEffect(() => {
    api.task(id).then((d) => { setT(d); setError(""); }).catch((e) => setError(String(e)));
  }, [id, tick]);
  useEffect(() => { setFocus(null); setOpen(new Set()); setDiff(null); setDiffOpen(false); }, [id]);
  useEffect(() => {
    if (diffOpen) api.diff(id).then(setDiff).catch((e) => setError(String(e)));
  }, [id, diffOpen, tick]);
  useEffect(() => {
    if (!text) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setText(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [text]);

  if (error && !t) return <p className="error">{error}</p>;
  if (!t) return <div className="panel skeleton" aria-busy="true" aria-label="Loading task" />;

  const review = t.reviews[t.reviews.length - 1];
  const statusOf = (cid: string) => review?.criteria_results.find((r) => r.criterion_id === cid);
  const job = t.job?.state === "running" ? t.job : null;
  const seen: Record<string, number> = {};
  const rows = t.rows.map((r, i) => {
    const op = r.invocation?.operation_id;
    const turn = op ? (seen[op] = (seen[op] ?? 0) + 1) : 0;
    return { ...r, i, turn };
  });
  const shown = focus ? rows.filter((r) => focus.steps.includes(r.step)) : rows;
  const newRows = fresh(t.rows.map((r) => `${r.at}|${r.kind}|${r.step}`));
  const maxCost = Math.max(...t.totals.map((x) => x.cost_usd), 0.0001);
  const t0 = t.rows.length ? new Date(t.rows[0].at).getTime() : 0;
  const met = review ? review.criteria_results.filter((r) => r.status === "met").length : 0;

  async function act(fn: (id: string) => Promise<unknown>) {
    try { await fn(id); onChange(); } catch (e) { setError(String(e).replace(/^Error: /, "")); }
  }
  async function show(title: string, sha: string) {
    try { const { text: body } = await api.text(sha); setText({ title, body: pretty(body) }); }
    catch (e) { setError(String(e)); }
  }
  const toggle = (i: number) => setOpen((s) => {
    const n = new Set(s); if (n.has(i)) n.delete(i); else n.add(i); return n;
  });

  return (
    <>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <a className="back" href="#/tasks">← All tasks</a>
          <h1 className="page-title">{taskName(t.title, t.task.description)}</h1>
          <p className="page-sub">{taskSummary(t.task.description, t.status, t.verdict).split(" · ").slice(1).join(" · ")}</p>
          <div className="row-meta" style={{ marginTop: 14 }}>
            <StatusDot status={t.status} />
            {t.verdict && <VerdictBadge verdict={t.verdict} />}
            {job && <span className="status live"><i />{job.action === "run" ? "Agents are working" : `${job.action} in progress`}</span>}
          </div>
        </div>
        <div className="actions">
          {t.status === "held" && <a className="btn primary" href="#/approvals">Answer the budget question</a>}
          {t.status === "created" && !job && (
            <>
              <label className="cap-input" title="Optional: spend less than the usual limit on this one">
                <span className="muted small">Spend up to $</span>
                <input inputMode="decimal" placeholder={String(t.task.budget.task_limit_usd)} value={cap}
                       aria-label="Most to spend on this run, in dollars"
                       onChange={(e) => setCap(e.target.value.replace(/[^0-9.]/g, ""))} />
              </label>
              <label className="toggle" title="Use lessons from earlier tasks, and learn from this one">
                <input type="checkbox" checked={learnOn} onChange={(e) => setLearnOn(e.target.checked)} />
                <span>Learn from this</span>
              </label>
              <button className="btn primary"
                      onClick={() => act((i) => api.run(i, cap ? Number(cap) : undefined, learnOn ? "lessons" : undefined))}>
                Start working on it
              </button>
            </>
          )}
          {t.status === "in_review" && !t.reviews.length && !job && (
            <button className="btn primary" onClick={() => act(api.review)}>Ask Guardian to review</button>
          )}
          {["running", "in_review"].includes(t.status) && !job && (
            <button className="btn" onClick={() => act(api.resume)}>Pick up where it left off</button>
          )}
          {["done", "escalated"].includes(t.status) && !job && !t.rows.some((r) => r.kind === "lessons_learned") && (
            <button className="btn" onClick={() => act(api.learn)}>Learn from this task</button>
          )}
          {!["done", "escalated", "failed"].includes(t.status) && !job && (
            <button className="btn ghost" onClick={() => {
              if (confirm("Close this task? Its work stays saved on its branch.")) act(api.abandon);
            }}>Close task</button>
          )}
        </div>
      </div>
      {error && <p className="error" style={{ margin: "0 0 12px" }}>{error}</p>}
      {t.job?.state === "failed" && <p className="error" style={{ marginBottom: 12 }}>{t.job.error}</p>}

      <Panel title="How the agents worked on it" flat
             right={focus
               ? <button className="link small" onClick={() => setFocus(null)}>Show all steps</button>
               : <span className="muted small">Tap an agent to see just its steps</span>}>
        <Pipeline rows={t.rows} running={!!job} status={t.status} selected={focus?.key ?? null}
                  onSelect={(key, steps) => setFocus(key ? { key, steps } : null)} />
        <Counters t={t} limits={system?.limits} />
      </Panel>

      <div className="grid2">
        <Panel title="What it had to do"
               right={review && <span className="muted small">{met} of {t.task.acceptance_criteria.length} passed</span>}>
          <ul className="checks">
            {t.task.acceptance_criteria.map((c) => {
              const r = statusOf(c.id);
              const st = r?.status ?? "";
              return (
                <li key={c.id}>
                  <div>
                    <p>{c.text}</p>
                    <span className="muted small">{IMPORTANCE[c.severity] ?? c.severity}</span>
                    {r?.evidence && st !== "met" && <p className="small dim" style={{ marginTop: 4 }}>{r.evidence}</p>}
                  </div>
                  <span className={`result ${st || "pending"}`}>
                    {st === "met" ? "Passed" : st === "unmet" ? "Not passed" : st ? "Couldn't check" : "Not checked yet"}
                  </span>
                </li>
              );
            })}
          </ul>
          {!!t.task.constraints.length && (
            <div className="rules-note">
              <span className="muted small">And without breaking these rules:</span>
              <ul>{t.task.constraints.map((c) => <li key={c} className="small">{c}</li>)}</ul>
            </div>
          )}
        </Panel>
        <Panel title="What it cost">
          <Meter value={t.spend_usd} max={t.task.budget.task_limit_usd}
                 label={<span className="cost-big">{usd(t.spend_usd, 3)}</span>}
                 right={<span className="muted small">of the {usd(t.task.budget.task_limit_usd, 0)} limit</span>} />
          <div className="bars">
            {t.totals.map((x) => (
              <div key={x.operation} className="bar-row">
                <span className="small clip">{agentName(x.operation)}</span>
                <div className="bar"><div style={{ transform: `scaleX(${x.cost_usd / maxCost})` }} /></div>
                <span className="small r num">{usd(x.cost_usd, 3)}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      {t.reviews.map((r, i) => (
        <Panel key={i} style={{ marginTop: 16 }}
               title={<span className="row-meta">{t.reviews.length > 1 ? `Guardian's review ${i + 1}` : "Guardian's review"} <VerdictBadge verdict={r.verdict} /></span>}>
          {r.summary && <p>{r.summary}</p>}
          {system && (
            <p className="small verdict-why">
              Why {r.verdict}: {system.verdict_rules.find((x) => x.rule === r.matched_rule)?.when}
            </p>
          )}
          {r.findings.map((f) => (
            <div key={f.code} className="finding small">
              <span className={`result ${f.severity === "minor" ? "pending" : "unmet"}`}>{f.severity === "minor" ? "Note" : "Issue"}</span>
              <span>{f.message}</span>
            </div>
          ))}
          {!!r.required_corrections.length && (
            <>
              <p className="small muted" style={{ marginTop: 12 }}>Guardian asked Builder to:</p>
              <ul className="corrections small">{r.required_corrections.map((c) => <li key={c}>{c}</li>)}</ul>
            </>
          )}
        </Panel>
      ))}

      <Panel id="trace" style={{ marginTop: 16 }} body={false}
             title={focus ? `Step by step · ${focus.key.split(":")[1]}` : "Step by step"}
             right={<span className="muted small">{focus ? `${shown.length} of ${t.rows.length} steps` : `${t.rows.length} steps`}</span>}>
        <ol className="story" aria-label="Every step, in order">
          {!shown.length && <li className="muted small" style={{ padding: 20 }}>This agent hasn't worked on this task.</li>}
          {shown.map((row, n) => (
            <StoryRow key={row.i} row={row} turn={row.turn} t0={t0} open={open.has(row.i)} onToggle={() => toggle(row.i)}
                      onShow={show} fresh={newRows.has(`${row.at}|${row.kind}|${row.step}`)} index={n} />
          ))}
        </ol>
      </Panel>

      <Panel style={{ marginTop: 16 }} body={false} title="What changed in the code"
             right={<button className="btn ghost" onClick={() => setDiffOpen((o) => !o)} aria-expanded={diffOpen}>
               {diffOpen ? "Hide changes" : "See the changes"}</button>}>
        {diffOpen && (diff === null
          ? <p className="muted small" style={{ padding: 20 }}>Loading the changes…</p>
          : diff.diff
            ? <Diff text={diff.diff} truncated={diff.truncated} />
            : <p className="muted small" style={{ padding: 20 }}>{diff.note ?? "Nothing has changed yet."}</p>)}
      </Panel>

      {text && (
        <div className="modal" onClick={() => setText(null)} role="dialog" aria-modal="true" aria-label={text.title}>
          <div className="panel modal-body" onClick={(e) => e.stopPropagation()}>
            <header className="panel-head">
              <h3 className="section-title">{text.title}</h3>
              <button className="btn ghost" autoFocus onClick={() => setText(null)}>Close</button>
            </header>
            <pre>{text.body}</pre>
          </div>
        </div>
      )}
    </>
  );
}

function StoryRow({ row, turn, t0, open, onToggle, onShow, fresh, index }: {
  row: TraceRow; turn: number; t0: number; open: boolean; onToggle: () => void; fresh: boolean; index: number;
  onShow: (title: string, sha: string) => void;
}) {
  const inv = row.invocation;
  const agent = agentOfStep(row.step);
  const who = agent ? AGENT[agent].short : "Ezra";
  const secs = Math.max(0, Math.round((new Date(row.at).getTime() - t0) / 1000));
  const when = secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${secs % 60}s`;
  const label = inv ? OPERATION_LABEL[inv.operation_id] ?? inv.operation_id : "";
  const sentence = inv ? (turn > 1 ? `${label}, round ${turn}` : label)
    : eventSentence(row.kind, row.data ?? {}, row.detail);
  const body = (
    <>
      <span className="story-time">{when}</span>
      <span className="story-who">{who}</span>
      <span className="story-what">{sentence}</span>
      {inv && <span className="story-meta">{modelName(inv.model_id)} · {(inv.latency_ms / 1000).toFixed(1)}s · {usd(inv.actual_cost_usd, 3)}<span className="chev" aria-hidden>›</span></span>}
    </>
  );
  return (
    <li className={`story-row ${inv ? "call" : "event"} ${open ? "open" : ""} ${fresh ? "fresh" : ""}`}
        style={{ "--i": index } as CSSProperties}>
      {inv ? <button className="story-main" onClick={onToggle} aria-expanded={open}>{body}</button>
           : <div className="story-main">{body}</div>}
      {inv && (
        <div className="ledger-more" aria-hidden={!open}>
          <div>
            <div className="story-detail small">
              <p className="dim">
                Read {fmt(inv.input_tokens + inv.cache_read_tokens + inv.cache_creation_tokens)} tokens
                ({fmt(inv.cache_read_tokens)} reused from cache) and wrote {fmt(inv.output_tokens)}.
                {inv.prompt_version && <> Instructions version <span className="soft-code">{inv.prompt_version.split("@")[1]}</span>.</>}
              </p>
              {!!inv.context.length && (
                <div className="chips">
                  <span className="muted">What it was given:</span>
                  {inv.context.map((c) => (
                    <button key={c.sha + c.label} className="chip" tabIndex={open ? 0 : -1}
                            onClick={() => onShow(CONTEXT_LABEL[c.label] ?? c.label, c.sha)}>
                      {CONTEXT_LABEL[c.label] ?? c.label.replace(/_/g, " ")}
                    </button>
                  ))}
                </div>
              )}
              {inv.response_hash && (
                <button className="chip reply" tabIndex={open ? 0 : -1}
                        onClick={() => onShow(`What ${who} said`, inv.response_hash!)}>
                  Read what it said →
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </li>
  );
}

const fmt = (n: number) => n.toLocaleString();

/** D-004's loop counters, in plain words. */
function Counters({ t, limits }: { t: TaskDetail; limits?: Record<string, number> }) {
  const kinds = t.rows.map((r) => r.kind);
  const fixes = kinds.filter((k) => k === "adjudicated").length;
  const revisions = kinds.filter((k) => k === "revision_started").length;
  const iterCap = limits?.internal_iteration_cap ?? 2;
  const cycleCap = limits?.correction_cycle_limit ?? 1;
  return (
    <div className="counters">
      <span className={`counter ${fixes >= iterCap ? "spent" : ""}`}>Fix attempts <b>{fixes} of {iterCap}</b></span>
      <span className={`counter ${revisions >= cycleCap ? "spent" : ""}`}>Sent back by Guardian <b>{revisions} of {cycleCap}</b></span>
      <span className="counter">Budget questions <b>{t.approvals.length}</b></span>
    </div>
  );
}

function Diff({ text, truncated }: { text: string; truncated?: boolean }) {
  const lines = text.split("\n");
  return (
    <div className="diff" role="region" aria-label="Code changes" tabIndex={0}>
      {lines.map((l, i) => {
        const cls = l.startsWith("diff --git") ? "file" : l.startsWith("@@") ? "hunk"
          : l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : "";
        if (l.startsWith("index ") || l.startsWith("+++") || l.startsWith("---") || l.startsWith("new file mode")) return null;
        return <div key={i} className={cls}>{cls === "file" ? l.replace(/^diff --git a\/(\S+).*$/, "$1") : l || " "}</div>;
      })}
      {truncated && <div className="muted">… cut at 300 KB</div>}
    </div>
  );
}

function agentName(op: string) {
  const a = agentOfOperation(op);
  if (!a) return op;
  return op.endsWith("adjudicate") ? "Code Joe (judging)" : AGENT[a].short;
}
function prettyJson(s: string) {
  try { return JSON.stringify(JSON.parse(s), null, 2); } catch { return s; }
}
function pretty(body: string): string {
  // Replies are stored as JSON content blocks; show their text, readable.
  try {
    const blocks = JSON.parse(body);
    if (Array.isArray(blocks)) {
      return blocks.map((b) => b.text !== undefined ? prettyJson(b.text) : (b.type === "tool_use"
        ? `[${b.name}] ${JSON.stringify(b.input, null, 2)}` : JSON.stringify(b, null, 2))).join("\n\n");
    }
  } catch { /* plain text */ }
  return body;
}

