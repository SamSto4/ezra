import type { Status } from "../api";
import { usd } from "../api";
import type { Route } from "../App";
import { Meter, Star } from "./bits";

const NAV: { view: Route["view"]; label: string; icon: string }[] = [
  { view: "home", label: "Home", icon: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" },
  { view: "agents", label: "Agents", icon: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0" },
  { view: "tasks", label: "Tasks", icon: "M4 6h16M4 12h16M4 18h10" },
  { view: "approvals", label: "Approvals", icon: "M5 12.5l4 4L19 7" },
  { view: "lessons", label: "Lessons", icon: "M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5z" },
  { view: "system", label: "Settings & info", icon: "M4 7h10M18 7h2M4 17h4M12 17h8M14 5v4M8 15v4" },
];

export function Sidebar({ route, status, online }:
  { route: Route; status: Status | null; online: boolean }) {
  const active = route.view === "task" ? "tasks" : route.view;
  const busy = status?.running.length ?? 0;
  return (
    <nav className="sidebar" aria-label="Main">
      <a className="brand" href="#/home" aria-label="Ezra home">
        <Star size={30} />
        <span className="brand-name">Ezra</span>
      </a>
      <ul className="nav">
        {NAV.map((n) => (
          <li key={n.view}>
            <a href={`#/${n.view}`} className={active === n.view ? "active" : ""}
               aria-current={active === n.view ? "page" : undefined}>
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
                <path d={n.icon} fill="none" stroke="currentColor" strokeWidth="1.7"
                      strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {n.label}
              {n.view === "approvals" && !!status?.pending_approvals && (
                <span className="count" aria-label={`${status.pending_approvals} waiting`}>
                  {status.pending_approvals}
                </span>
              )}
            </a>
          </li>
        ))}
      </ul>
      <div className="presence">
        <span className={`status ${!online ? "bad" : busy ? "live" : "ok"}`}>
          <i />{!online ? "Offline" : busy ? `Working on ${busy} task${busy > 1 ? "s" : ""}` : "Ready"}
        </span>
        {!online && <p className="muted small" style={{ marginTop: 8 }}>Start it with <span className="mono">ezra ui</span></p>}
        {status && (
          <div style={{ marginTop: 14 }}>
            <Meter value={status.spent_today_usd} max={status.daily_limit_usd}
                   label={<span className="muted">Spent today</span>}
                   right={<span>{usd(status.spent_today_usd, 2)}
                     <span className="muted"> of {usd(status.daily_limit_usd, 0)}</span></span>} />
            <p className="muted small" style={{ marginTop: 8 }}>Up to {usd(status.task_limit_usd, 0)} per task</p>
          </div>
        )}
      </div>
    </nav>
  );
}
