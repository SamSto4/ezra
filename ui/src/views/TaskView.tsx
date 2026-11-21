import { useEffect, useState, type CSSProperties } from "react";
import { AGENT, agentOfOperation, agentOfStep } from "../agents";
import { api, usd, type SystemInfo, type TaskDetail, type TraceRow } from "../api";
import { clock, Eyebrow, Meter, Panel, StatusDot, useFresh, VerdictBadge } from "../components/bits";
import { Pipeline, type NodeKey } from "../components/Pipeline";

export function TaskView({ id, tick, onChange, system }:
  { id: string; tick: number; onChange: () => void; system: SystemInfo | null }) {
  const [cap, setCap] = useState("");
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
  const rows = t.rows.map((r, i) => ({ ...r, i }));
  const shown = focus ? rows.filter((r) => focus.steps.includes(r.step)) : rows;
  const newRows = fresh(t.rows.map((r) => `${r.at}|${r.kind}|${r.step}`));
  const maxCost = Math.max(...t.totals.map((x) => x.cost_usd), 0.0001);

  async function act(fn: (id: string) => Promise<unknown>) {
    try { await fn(id); onChange(); } catch (e) { setError(String(e)); }
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
          <Eyebrow>Task · <span style={{ textTransform: "none" }}>{t.task.task_id}</span></Eyebrow>
          <h1 className="page-title task">{t.task.description}</h1>
          <div className="row-meta" style={{ marginTop: 12 }}>
            <StatusDot status={t.status} />
            <VerdictBadge verdict={t.verdict} />
            <span className="mono muted">ezra/{t.task.task_id}</span>
            {job && <span className="status live"><i />{job.action} in progress</span>}
          </div>
        </div>
        <div className="actions">
          {t.status === "held" && <a className="btn primary" href="#/approvals">Answer the HOLD</a>}
          {t.status === "created" && !job && (
            <>
              <label className="cap-input" title="Optional: lower this run's budget cap">
                <span className="muted small">Cap $</span>
                <input inputMode="decimal" placeholder={String(t.task.budget.task_limit_usd)} value={cap}
                       aria-label="Budget cap for this run, in dollars"
                       onChange={(e) => setCap(e.target.value.replace(/[^0-9.]/g, ""))} />
              </label>
              <button className="btn primary" onClick={() => act((i) => api.run(i, cap ? Number(cap) : undefined))}>
                Run with Code Joe
              </button>
            </>
          )}
          {t.status === "in_review" && !t.reviews.length && !job && (
            <button className="btn primary" onClick={() => act(api.review)}>Review</button>
          )}
          {["running", "in_review"].includes(t.status) && !job && (
            <button className="btn" onClick={() => act(api.resume)}>Resume</button>
          )}
          {!["done", "escalated", "failed"].includes(t.status) && !job && (
            <button className="btn ghost" onClick={() => {
              if (confirm("Close this task as failed? Its branch is kept.")) act(api.abandon);
            }}>Abandon</button>
          )}
        </div>
      </div>
      <Counters t={t} limits={system?.limits} />
      {error && <p className="error" style={{ margin: "12px 0" }}>{error}</p>}
      {t.job?.state === "failed" && <p className="error" style={{ marginBottom: 12 }}>{t.job.error}</p>}

      <Panel eyebrow={<Eyebrow>Agent pipeline</Eyebrow>} flat
             right={focus
               ? <button className="link small" onClick={() => setFocus(null)}>Show every step</button>
               : <span className="muted small">Select an agent to filter the trace</span>}>
        <Pipeline rows={t.rows} running={!!job} status={t.status} selected={focus?.key ?? null}
                  onSelect={(key, steps) => setFocus(key ? { key, steps } : null)} />
      </Panel>

      <div className="grid2">
        <Panel title="Acceptance criteria"
               right={review && <span className="muted small">
                 {review.criteria_results.filter((r) => r.status === "met").length}
                 /{t.task.acceptance_criteria.length} met</span>}>
          <ul className="criteria">
            {t.task.acceptance_criteria.map((c) => {
              const r = statusOf(c.id);
              return (
                <li key={c.id} title={r?.evidence}>
                  <span className={`tick ${r?.status ?? ""}`} aria-label={r?.status ?? "not judged yet"} />
                  <span className="mono muted">{c.id}</span>
                  <span className={`sev ${c.severity}`}>{c.severity}</span>
                  <span>{c.text}</span>
                </li>
              );
            })}
          </ul>
          {t.task.constraints.map((c) => <p key={c} className="muted small" style={{ marginTop: 10 }}>Constraint · {c}</p>)}
        </Panel>
        <Panel title="Cost">
          <Meter value={t.spend_usd} max={t.task.budget.task_limit_usd}
                 label={<span className="mono">{usd(t.spend_usd)}</span>}
                 right={<span className="muted small">of {usd(t.task.budget.task_limit_usd, 2)} budget</span>} />
          <div className="bars">
            {t.totals.map((x) => (
              <div key={x.operation} className="bar-row" style={{ "--hue": hueOfOp(x.operation) } as CSSProperties}>
                <span className="agent-tag clip" data-g={glyphOfOp(x.operation)}>{agentName(x.operation)}</span>
                <div className="bar"><div style={{ transform: `scaleX(${x.cost_usd / maxCost})` }} /></div>
                <span className="mono r">{usd(x.cost_usd)}</span>
              </div>
            ))}
          </div>
          <p className="muted small" style={{ marginTop: 14 }}>{t.calls} model calls</p>
        </Panel>
      </div>

      {t.reviews.map((r, i) => (
        <Panel key={i} style={{ marginTop: 16 }}
               title={<span className="row-meta">Guardian review {i + 1} <VerdictBadge verdict={r.verdict} /></span>}
               right={<span className="mono muted">rule {r.matched_rule} · {r.tier.replace("_", " ")}</span>}>
          {r.summary && <p className="dim">{r.summary}</p>}
          {system && (
            <p className="small verdict-why">
              <span className="mono">Rule {r.matched_rule}</span> · {system.verdict_rules.find((x) => x.rule === r.matched_rule)?.when}
            </p>
          )}
          {r.findings.map((f) => (
            <div key={f.code} className="finding small">
              <span className={`sev ${f.severity}`}>{f.severity}</span>
              <span><b>{f.code}</b> · {f.message}</span>
            </div>
          ))}
          {!!r.required_corrections.length && (
            <ul className="corrections small">{r.required_corrections.map((c) => <li key={c}>{c}</li>)}</ul>
          )}
        </Panel>
      ))}

      <Panel id="trace" style={{ marginTop: 16 }} body={false}
             title={focus ? `Trace · ${focus.key.split(":")[1]}` : "Trace"}
             right={<span className="muted small">
               {focus ? `${shown.length} of ${t.rows.length} steps` : `${t.rows.length} steps`}</span>}>
        <div className="ledger" role="table" aria-label="Trace">
          <div className="ledger-head" role="row">
            <span>Time</span><span>Agent</span><span>What happened</span>
            <span className="hide-md">Model</span><span className="r hide-md">Tokens</span>
            <span className="r">Cost</span><span className="r hide-md">Time</span>
          </div>
          {!shown.length && <p className="muted small" style={{ padding: 20 }}>This agent hasn't run on this task.</p>}
          {shown.map((row, n) => (
            <LedgerRow key={row.i} row={row} open={open.has(row.i)} onToggle={() => toggle(row.i)}
                       onShow={show} fresh={newRows.has(`${row.at}|${row.kind}|${row.step}`)} index={n} />
          ))}
        </div>
      </Panel>

      <Panel style={{ marginTop: 16 }} body={false} title="Changes on the branch"
             right={<button className="btn ghost" onClick={() => setDiffOpen((o) => !o)} aria-expanded={diffOpen}>
               {diffOpen ? "Hide diff" : "Show diff"}</button>}>
        {diffOpen && (diff === null
          ? <p className="muted small" style={{ padding: 20 }}>Loading the diff…</p>
          : diff.diff
            ? <Diff text={diff.diff} truncated={diff.truncated} />
            : <p className="muted small" style={{ padding: 20 }}>{diff.note ?? "No changes yet."}</p>)}
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

function LedgerRow({ row, open, onToggle, onShow, fresh, index }: {
  row: TraceRow; open: boolean; onToggle: () => void; fresh: boolean; index: number;
  onShow: (title: string, sha: string) => void;
}) {
  const inv = row.invocation;
  const agent = agentOfStep(row.step);
  const hue = agent ? AGENT[agent].hue : "var(--muted)";
  const cells = (
    <>
      <span className="mono muted">{clock(row.at)}</span>
      <span className="agent-tag" data-g={agent ? AGENT[agent].glyph : "··"} style={{ "--hue": hue } as CSSProperties}>
        {agent ? AGENT[agent].short : row.step}
      </span>
      {inv ? (
        <span className="clip"><span className="chev" aria-hidden>›</span><span className="mono">{inv.operation_id}</span></span>
      ) : <span className="clip span-rest" title={row.detail}>{row.detail}</span>}
      {inv && <>
        <span className="mono dim hide-md">{inv.model_id.replace("claude-", "")}</span>
        <span className="mono dim r hide-md">{inv.input_tokens + inv.cache_read_tokens + inv.cache_creation_tokens} / {inv.output_tokens}</span>
        <span className="mono r">{usd(inv.actual_cost_usd)}</span>
        <span className="mono muted r hide-md">{(inv.latency_ms / 1000).toFixed(1)}s</span>
      </>}
    </>
  );
  return (
    <div className={`ledger-row ${inv ? "call" : "event"} ${open ? "open" : ""} ${fresh ? "fresh" : ""}`}
         style={{ "--i": index } as CSSProperties} role="row">
      {inv ? (
        <button className="ledger-main" onClick={onToggle} aria-expanded={open}>{cells}</button>
      ) : <div className="ledger-main">{cells}</div>}
      {inv && (
        <div className="ledger-more" aria-hidden={!open}>
          <div>
            <div className="ledger-detail small">
              <span className="muted">Prompt</span>
              <span className="mono">{inv.prompt_version || "(not recorded)"}</span>
              <span className="muted" style={{ marginLeft: 8 }}>
                Cache read {inv.cache_read_tokens} · write {inv.cache_creation_tokens}
              </span>
              <span style={{ flexBasis: "100%", height: 0 }} />
              {inv.context.map((c) => (
                <button key={c.sha + c.label} className="chip" tabIndex={open ? 0 : -1}
                        onClick={() => onShow(c.label.replace("_", " "), c.sha)}>
                  {c.label} · {c.chars}
                </button>
              ))}
              {inv.response_hash && (
                <button className="chip reply" tabIndex={open ? 0 : -1}
                        onClick={() => onShow(`Reply · ${inv.operation_id}`, inv.response_hash!)}>
                  Open reply →
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** D-004's counters for this task, read from what the trace shows happened. */
function Counters({ t, limits }: { t: TaskDetail; limits?: Record<string, number> }) {
  const kinds = t.rows.map((r) => r.kind);
  const fixes = kinds.filter((k) => k === "adjudicated").length;
  const revisions = kinds.filter((k) => k === "revision_started").length;
  const holds = t.approvals.length;
  const iterCap = limits?.internal_iteration_cap ?? 2;
  const cycleCap = limits?.correction_cycle_limit ?? 1;
  return (
    <div className="counters" aria-label="Loop counters">
      <span className={`counter ${fixes >= iterCap ? "spent" : ""}`}>Fix rounds <b>{fixes}/{iterCap}</b></span>
      <span className={`counter ${revisions >= cycleCap ? "spent" : ""}`}>Correction cycles <b>{revisions}/{cycleCap}</b></span>
      <span className="counter">Reviews <b>{t.reviews.length}</b></span>
      <span className="counter">HOLDs <b>{holds}</b></span>
      <span className="counter">Model calls <b>{t.calls}</b></span>
    </div>
  );
}

function Diff({ text, truncated }: { text: string; truncated?: boolean }) {
  const lines = text.split("\n");
  return (
    <div className="diff" role="region" aria-label="Diff" tabIndex={0}>
      {lines.map((l, i) => {
        const cls = l.startsWith("diff --git") ? "file" : l.startsWith("@@") ? "hunk"
          : l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : "";
        if (l.startsWith("index ") || l.startsWith("+++") || l.startsWith("---")) return null;
        return <div key={i} className={cls}>{cls === "file" ? l.replace(/^diff --git a\/(\S+).*$/, "$1") : l || " "}</div>;
      })}
      {truncated && <div className="muted">… cut at 300 KB</div>}
    </div>
  );
}

function agentName(op: string) {
  const a = agentOfOperation(op);
  return a ? `${AGENT[a].short}${op.endsWith("adjudicate") ? " · judge" : ""}` : op;
}
function glyphOfOp(op: string) {
  const a = agentOfOperation(op);
  return a ? AGENT[a].glyph : "··";
}
function hueOfOp(op: string) {
  const a = agentOfOperation(op);
  return a ? AGENT[a].hue : "var(--accent)";
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
