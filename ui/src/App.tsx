import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { api, subscribe, type EzraEvent, type Status, type SystemInfo, type TaskSummary } from "./api";
import { Sidebar } from "./components/Sidebar";
import { Home } from "./views/Home";
import { TaskView } from "./views/TaskView";
import { TasksView } from "./views/TasksView";
import { ApprovalsView } from "./views/ApprovalsView";
import { AgentsView } from "./views/AgentsView";
import { SystemView } from "./views/SystemView";
import { LessonsView } from "./views/LessonsView";
import { ActivityPanel } from "./components/ActivityPanel";

export type Route =
  | { view: "home" }
  | { view: "tasks" }
  | { view: "approvals" }
  | { view: "agents" }
  | { view: "system" }
  | { view: "lessons" }
  | { view: "task"; id: string };

function parseHash(): Route {
  const h = window.location.hash.replace(/^#\/?/, "");
  if (h.startsWith("task/")) return { view: "task", id: h.slice(5) };
  if (h === "tasks" || h === "approvals" || h === "agents" || h === "system" || h === "lessons") return { view: h };
  return { view: "home" };
}

export function go(route: Route) {
  window.location.hash = route.view === "task" ? `/task/${route.id}` : `/${route.view}`;
}

export default function App() {
  const [route, setRoute] = useState<Route>(parseHash);
  const [status, setStatus] = useState<Status | null>(null);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [events, setEvents] = useState<EzraEvent[]>([]);
  const [tick, setTick] = useState(0); // bumps on every live event: views refetch
  const [online, setOnline] = useState(true);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    // Crossfade between views (View Transitions API), instant where unsupported.
    const onHash = () => {
      const next = parseHash();
      const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (doc.startViewTransition && !reduce) doc.startViewTransition(() => flushSync(() => setRoute(next)));
      else setRoute(next);
      document.querySelector(".main")?.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([api.status(), api.tasks()]);
      setStatus(s);
      setTasks(t);
      setOnline(true);
    } catch {
      setOnline(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh, tick]);
  useEffect(() => { api.system().then(setSystem).catch(() => undefined); }, [tick]);

  // One live stream for the whole app. Bursts of events are batched into one refetch.
  useEffect(() => {
    let close: (() => void) | undefined;
    api.status().then((s) => {
      close = subscribe((e) => {
        setEvents((prev) => [...prev.slice(-199), e]);
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setTick((n) => n + 1), 250);
      }, s.last_event_id);
    }).catch(() => setOnline(false));
    return () => close?.();
  }, []);

  // Jobs started from the UI finish without an event when they fail early; poll gently
  // while anything runs so the page never looks stuck.
  useEffect(() => {
    if (!status?.running.length) return;
    const id = window.setInterval(() => setTick((n) => n + 1), 3000);
    return () => window.clearInterval(id);
  }, [status?.running.length]);

  const bump = () => setTick((n) => n + 1);

  return (
    <div className="shell">
      <Sidebar route={route} status={status} online={online} />
      <main className="main"><div className="main-inner">
        {route.view === "home" && <Home tasks={tasks} onChange={bump} tick={tick} events={events}
                                         cacheSaved={system?.cache_saved_usd ?? null} />}
        {route.view === "tasks" && <TasksView tasks={tasks} />}
        {route.view === "agents" && <AgentsView tick={tick} events={events} />}
        {route.view === "system" && <SystemView system={system} status={status} />}
        {route.view === "lessons" && <LessonsView tick={tick} onChange={bump} />}
        {route.view === "approvals" && <ApprovalsView tick={tick} onChange={bump} />}
        {route.view === "task" && <TaskView id={route.id} tick={tick} onChange={bump} system={system} />}
      </div></main>
      <aside className="rail">
        <ActivityPanel events={events} tasks={tasks} />
      </aside>
    </div>
  );
}
