import { useEffect, useState } from "react";
import { api, type Approval } from "../api";
import { ago, Eyebrow, Panel } from "../components/bits";

// D-009 Level 1 decisions wait here. Answering one resumes its task.
export function ApprovalsView({ tick, onChange }: { tick: number; onChange: () => void }) {
  const [items, setItems] = useState<Approval[] | null>(null);
  const [error, setError] = useState("");
  const [sent, setSent] = useState<Record<string, string>>({});
  const [extend, setExtend] = useState<Record<string, string>>({});

  useEffect(() => { api.approvals().then(setItems).catch((e) => setError(String(e))); }, [tick]);

  async function answer(a: Approval, approved: boolean) {
    try {
      const x = extend[a.approval_id];
      await api.answer(a.approval_id, approved, approved && x ? Number(x) : undefined);
      setSent((s) => ({ ...s, [a.approval_id]: approved ? "Approved" : "Rejected" }));
      onChange();
    } catch (e) { setError(String(e)); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <Eyebrow dot="var(--warn)">Waiting on you</Eyebrow>
          <h1 className="page-title">Approvals</h1>
          <p className="page-sub">When an agent needs more budget than it's allowed, it pauses and asks you here.
            Say yes and it picks up right where it stopped.</p>
        </div>
      </div>
      {error && <p className="error" style={{ marginBottom: 12 }}>{error}</p>}
      {items === null && <div className="panel skeleton" style={{ minHeight: 120 }} aria-busy="true" />}
      {items?.length === 0 && (
        <Panel><p className="dim">Nothing needs you right now. You're all caught up.</p></Panel>
      )}
      {items?.map((a) => (
        <Panel key={a.approval_id} className="fresh"
               eyebrow={<Eyebrow dot="var(--warn)">{a.kind === "budget_hold" ? "Budget question" : a.kind.replace("_", " ")} · {ago(a.created_at)}</Eyebrow>}
               title={a.summary} flat>
          {a.task_id && <a href={`#/task/${a.task_id}`} className="dim small">Open the task →</a>}
          <div className="actions" style={{ marginTop: 14 }}>
            {sent[a.approval_id]
              ? <span className="status live"><i />{sent[a.approval_id] === "Approved" ? "Thanks. The agents are picking it back up…" : "Got it. The task will stop."}</span>
              : <>
                  <label className="cap-input" title="How much to raise the cap. Empty means just enough.">
                    <span className="muted small">Raise by $</span>
                    <input inputMode="decimal" placeholder="auto" value={extend[a.approval_id] ?? ""}
                           aria-label="How much to raise the budget cap, in dollars"
                           onChange={(e) => setExtend((s) => ({ ...s, [a.approval_id]: e.target.value.replace(/[^0-9.]/g, "") }))} />
                  </label>
                  <button className="btn primary" onClick={() => answer(a, true)}>Yes, carry on</button>
                  <button className="btn" onClick={() => answer(a, false)}>No, stop here</button>
                </>}
          </div>
        </Panel>
      ))}
    </>
  );
}
