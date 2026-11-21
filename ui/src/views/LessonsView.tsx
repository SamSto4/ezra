import { useEffect, useState } from "react";
import { api, type AgentInfo, type Lesson } from "../api";
import { ago, Eyebrow, Panel } from "../components/bits";

const FOR: Record<string, string> = {
  "code_joe.plan": "Code Joe, when planning", "builder.implement": "Builder, when writing code",
  "tester.write_tests": "Tester, when writing tests",
};
const KIND: Record<string, string> = { strategy: "What works", pitfall: "Watch out for", check: "Double-check" };

// What Ezra has learned from finished tasks (D-012 goal 3). Each lesson is short, scoped to
// one agent, and retired when it stops helping. Retiring one here is the one-step undo.
export function LessonsView({ tick, onChange }: { tick: number; onChange: () => void }) {
  const [lessons, setLessons] = useState<Lesson[] | null>(null);
  const [learner, setLearner] = useState<AgentInfo | null>(null);
  const [error, setError] = useState("");
  const [showRetired, setShowRetired] = useState(false);

  useEffect(() => {
    api.lessons().then(setLessons).catch((e) => setError(String(e)));
    api.agents().then((a) => setLearner(a.find((x) => x.id === "learner") ?? null)).catch(() => undefined);
  }, [tick]);

  const active = (lessons ?? []).filter((l) => l.status === "active").sort((a, b) => (b.helpful - b.harmful) - (a.helpful - a.harmful));
  const retired = (lessons ?? []).filter((l) => l.status === "retired");
  const memory = learner?.memory ?? "off";

  async function retire(l: Lesson) {
    if (!confirm("Stop using this lesson? It stays in the history.")) return;
    try { await api.retireLesson(l.lesson_id); onChange(); } catch (e) { setError(String(e)); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <Eyebrow dot={memory === "lessons" ? "var(--accent)" : "var(--muted)"}>
            {memory === "lessons" ? "Learning is on" : memory === "frozen" ? "Using lessons, not learning new ones" : "Learning is off"}
          </Eyebrow>
          <h1 className="page-title">Lessons</h1>
          <p className="page-sub">After a task, Learner looks at what Guardian found and writes down a short lesson for
            next time. A lesson is kept only if it passes a check, and it's retired if it keeps making things worse.</p>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {lessons === null && <div className="panel skeleton" style={{ minHeight: 140 }} aria-busy="true" />}

      {lessons !== null && !active.length && (
        <Panel>
          <p className="dim">No lessons yet.</p>
          <p className="muted small" style={{ marginTop: 8 }}>
            {memory === "off"
              ? "Learning is switched off by default. Tick \"Learn from this\" when you start a task, or use \"Learn from this task\" on a finished one."
              : "They'll appear here after the next finished task."}
          </p>
        </Panel>
      )}

      {active.map((l) => (
        <Panel key={l.lesson_id} className="fresh" flat
               eyebrow={<Eyebrow dot={l.kind === "pitfall" ? "var(--warn)" : "var(--primary)"}>{KIND[l.kind] ?? l.kind} · for {FOR[l.operation] ?? l.operation}</Eyebrow>}
               title={l.text}
               right={<button className="btn ghost" onClick={() => retire(l)}>Stop using</button>}>
          <p className="muted small">
            When {l.trigger.replace(/\.$/, "")}. Helped {l.helpful}×, hurt {l.harmful}×, shared in {l.uses} task{l.uses === 1 ? "" : "s"}
            {" "}· learned from {l.evidence.length} task{l.evidence.length === 1 ? "" : "s"} · updated {ago(l.updated_at)}
          </p>
        </Panel>
      ))}

      {!!retired.length && (
        <div style={{ marginTop: 20 }}>
          <button className="link small" onClick={() => setShowRetired((v) => !v)} aria-expanded={showRetired}>
            {showRetired ? "Hide" : "Show"} {retired.length} retired lesson{retired.length === 1 ? "" : "s"}
          </button>
          {showRetired && retired.map((l) => (
            <Panel key={l.lesson_id} flat style={{ marginTop: 12, opacity: 0.75 }}
                   eyebrow={<Eyebrow dot="var(--muted)">Retired · {FOR[l.operation] ?? l.operation}</Eyebrow>} title={l.text}>
              <p className="muted small">Helped {l.helpful}×, hurt {l.harmful}×.</p>
            </Panel>
          ))}
        </div>
      )}
    </>
  );
}
