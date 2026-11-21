import type { CSSProperties } from "react";
import { AGENT, type AgentId } from "../agents";
import type { AgentInfo } from "../api";
import { modelName } from "../humanize";

// Ezra's signature view: Ezra at the center, its agents around it, each labelled with the
// model it runs on and what it does. Curved spokes show who Ezra hands work to; a lime packet
// travels a spoke while that agent works. (Idea from Strike Drive's hub map, made calm in Volt.)

const W = 800, H = 460, CX = 400, CY = 230, RX = 300, RY = 168;
const RING: { id: AgentId; angle: number; short: string }[] = [
  { id: "code_joe", angle: -90, short: "Plans the change" },
  { id: "builder", angle: -24, short: "Writes the code" },
  { id: "tester", angle: 34, short: "Writes the tests" },
  { id: "checks", angle: 146, short: "Runs the tests" },
  { id: "guardian", angle: 204, short: "Reviews the work" },
  { id: "learner", angle: 90, short: "Learns for next time" },
];
const RING_PATH = `M${CX + RX},${CY} A${RX},${RY} 0 1,1 ${CX - RX},${CY} A${RX},${RY} 0 1,1 ${CX + RX},${CY}`;

function pos(angle: number) {
  const a = (angle * Math.PI) / 180;
  return { x: CX + RX * Math.cos(a), y: CY + RY * Math.sin(a) };
}

/** A gently curved spoke from the center to a pad. */
function spoke(x: number, y: number) {
  const mx = (CX + x) / 2, my = (CY + y) / 2;
  const nx = -(y - CY), ny = x - CX; // perpendicular
  const len = Math.hypot(nx, ny) || 1;
  const bend = 26;
  return `M${CX},${CY} Q${(mx + (nx / len) * bend).toFixed(1)},${(my + (ny / len) * bend).toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`;
}

export function Orbit({ agents, busy, onPick, selected, compact }: {
  agents: AgentInfo[] | null; busy: Set<AgentId>; onPick?: (id: AgentId) => void;
  selected?: AgentId; compact?: boolean;
}) {
  const by = Object.fromEntries((agents ?? []).map((a) => [a.id, a]));
  const model = (id: AgentId) => {
    if (id === "checks") return "No model needed";
    const a = by[id];
    return a ? [...new Set(a.operations.map((o) => modelName(o.model)))].join(" + ") : "";
  };
  const centerBusy = busy.has("intake");

  return (
    <div className={`orbit ${compact ? "compact" : ""}`} role="group" aria-label="Ezra and its agents">
      <svg viewBox={`0 0 ${W} ${H}`} className="orbit-svg" aria-hidden>
        <path d={RING_PATH} className="orbit-ring" />
        <ellipse cx={CX} cy={CY} rx={RX * 0.55} ry={RY * 0.55} className="orbit-ring faint" />
        <circle r="3" className="drift">
          <animateMotion dur="40s" repeatCount="indefinite" path={RING_PATH} />
        </circle>
        {RING.map(({ id, angle }) => {
          const p = pos(angle);
          const d = spoke(p.x, p.y);
          return (
            <g key={id}>
              <path d={d} className={`spoke ${busy.has(id) ? "live" : ""}`} />
              {busy.has(id) && (
                <circle r="5" className="packet">
                  <animateMotion dur="1.6s" repeatCount="indefinite" path={d} keyPoints="0;1" keyTimes="0;1"
                                 calcMode="spline" keySplines="0.4 0 0.2 1" />
                </circle>
              )}
            </g>
          );
        })}
      </svg>

      <button type="button" className={`orbit-core ${centerBusy ? "live" : ""} ${selected === "intake" ? "sel" : ""}`}
              style={{ left: `${(CX / W) * 100}%`, top: `${(CY / H) * 100}%` }}
              onClick={() => onPick?.("intake")}
              aria-label={`Ezra: reads your request and sends it to the right agent. Runs on ${model("intake")}.`}>
        <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
          <path d="M16 1 C17 11 21 15 31 16 C21 17 17 21 16 31 C15 21 11 17 1 16 C11 15 15 11 16 1 Z" />
        </svg>
        <span className="orbit-core-name">Ezra</span>
        <span className="pad-model">{centerBusy ? "Reading your request…" : model("intake")}</span>
      </button>

      {RING.map(({ id, angle, short }) => {
        const p = pos(angle);
        const live = busy.has(id);
        return (
          <button key={id} type="button" className={`pad ${live ? "live" : ""} ${selected === id ? "sel" : ""}`}
                  style={{ left: `${(p.x / W) * 100}%`, top: `${(p.y / H) * 100}%`, "--d": `${angle}ms` } as CSSProperties}
                  onClick={() => onPick?.(id)}
                  aria-label={`${AGENT[id].name}: ${AGENT[id].does}. ${model(id)}${live ? ". Working now" : ""}`}>
            <span className="pad-dot" aria-hidden />
            <span className="pad-text">
              <span className="pad-name">{AGENT[id].short}</span>
              <span className="pad-does">{live ? "Working now…" : short}</span>
              <span className="pad-model">{model(id)}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
