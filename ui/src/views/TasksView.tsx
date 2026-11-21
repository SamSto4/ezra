import { usd, type TaskSummary } from "../api";
import { ago, Eyebrow, Panel, StatusDot, VerdictBadge } from "../components/bits";
import { taskName, taskSummary } from "../humanize";

export function TasksView({ tasks }: { tasks: TaskSummary[] }) {
  const passed = tasks.filter((t) => t.verdict === "PASS");
  const spent = tasks.reduce((n, t) => n + t.spend_usd, 0);
  const perTask = passed.length ? passed.reduce((n, t) => n + t.spend_usd, 0) / passed.length : null;
  const go = (id: string) => { window.location.hash = `/task/${id}`; };
  return (
    <>
      <div className="page-head">
        <div>
          <Eyebrow>Everything Ezra has worked on</Eyebrow>
          <h1 className="page-title">Tasks</h1>
        </div>
      </div>
      <div className="stats">
        <div className="stat"><Eyebrow>Tasks</Eyebrow><div className="stat-value">{tasks.length}</div></div>
        <div className="stat"><Eyebrow dot="var(--ok)">Passed</Eyebrow><div className="stat-value">{passed.length}</div></div>
        <div className="stat"><Eyebrow>Per successful task</Eyebrow><div className="stat-value">{usd(perTask, 3)}</div></div>
        <div className="stat"><Eyebrow>Total spend</Eyebrow><div className="stat-value">{usd(spent, 2)}</div></div>
      </div>
      <Panel body={false}>
        {!tasks.length && <p className="muted" style={{ padding: 20 }}>No tasks yet. Ask Ezra to build something from Home.</p>}
        {!!tasks.length && (
          <table className="table">
            <thead>
              <tr><th>Task</th><th>Status</th><th>Review</th><th className="r">Cost</th><th className="r hide-sm">Started</th></tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.task_id} className="clickable" tabIndex={0} onClick={() => go(t.task_id)}
                    onKeyDown={(e) => { if (e.key === "Enter") go(t.task_id); }}>
                  <td className="task-cell">
                    <span className="task-name clip">{taskName(t.title, t.description)}</span>
                    <span className="task-sub clip">{taskSummary(t.description, t.status, t.verdict).split(" · ").slice(1).join(" · ")}</span>
                  </td>
                  <td><StatusDot status={t.status} /></td>
                  <td><VerdictBadge verdict={t.verdict} /></td>
                  <td className="r num">{usd(t.spend_usd, 3)}</td>
                  <td className="muted small r hide-sm">{ago(t.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </>
  );
}
