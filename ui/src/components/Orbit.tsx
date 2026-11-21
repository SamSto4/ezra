import type { CSSProperties } from "react";
import { AGENT, type AgentId } from "../agents";
import { usd, type AgentInfo } from "../api";

// Ezra's signature view: Ezra at the center, its agents in orbit, each one a "pad" with its
// live figures on it (an idea from Strike Drive's hub map, made flat and quiet in Volt).
// Spokes show who Ezra hands work to; a lime packet travels a spoke while that agent works.

const W = 800, H = 460, CX = 400, CY = 230;
const RING: { id: AgentId; angle: number }[] = [
  { id: "code_joe", angle: -90 },
  { id: "builder", angle: -24 },
  { id: "tester", angle: 34 },
  { id: "checks", angle: 146 },
  { id: "guardian", angle: 204 },
];
const RX = 300, RY = 168;

function pos(angle: number) {
  const a = (angle * Math.PI) / 180;
  return { x: CX + RX * Math.cos(a), y: CY + RY * Math.sin(a) };
}

export function Orbit({ agents, busy, onPick }: {
  agents: AgentInfo[] | null; busy: Set<AgentId>; onPick?: (id: AgentId) => void;
}) {
  const by = Object.fromEntries((agents ?? []).map((a) => [a.id, a]));
  const figure = (id: AgentId) => {
    if (id === "checks") return "no model · $0";
    const a = by[id];
    if (!a) return "—";
    return `${a.calls} call${a.calls === 1 ? "" : "s"} · ${usd(a.cost_usd, 3)}`;
  };
  const model = (id: AgentId) => {
    const a = by[id];
    if (id === "checks") return "pytest · ruff";
    return a ? [...new Set(a.operations.map((o) => o.model.replace("claude-", "")))].join(" / ") : "";
  };
  const centerBusy = busy.has("intake");

  return (
    <div className="orbit" role="group" aria-label="Ezra and its agents">
      <svg viewBox={`0 0 ${W} ${H}`} className="orbit-svg" aria-hidden>
        <ellipse cx={CX} cy={CY} rx={RX} ry={RY} className="orbit-ring" />
        <ellipse cx={CX} cy={CY} rx={RX * 0.55} ry={RY * 0.55} className="orbit-ring faint" />
        {RING.map(({ id, angle }) => {
          const p = pos(angle);
          return (
            <g key={id}>
              <line x1={CX} y1={CY} x2={p.x} y2={p.y} className={`spoke ${busy.has(id) ? "live" : ""}`} />
              {busy.has(id) && (
                <circle r="5" className="packet">
                  <animateMotion dur="1.4s" repeatCount="indefinite" path={`M${CX},${CY} L${p.x},${p.y}`} />
                </circle>
              )}
            </g>
          );
        })}
      </svg>

      <button type="button" className={`orbit-core ${centerBusy ? "live" : ""}`}
              style={{ left: `${(CX / W) * 100}%`, top: `${(CY / H) * 100}%` }}
              onClick={() => onPick?.("intake")}>
        <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden>
          <path d="M16 1 C17 11 21 15 31 16 C21 17 17 21 16 31 C15 21 11 17 1 16 C11 15 15 11 16 1 Z" />
        </svg>
        <span className="orbit-core-name">Ezra</span>
        <span className="orbit-fig">{figure("intake")}</span>
      </button>

      {RING.map(({ id, angle }) => {
        const p = pos(angle);
        const live = busy.has(id);
        return (
          <button key={id} type="button" className={`pad ${live ? "live" : ""}`}
                  style={{ left: `${(p.x / W) * 100}%`, top: `${(p.y / H) * 100}%` } as CSSProperties}
                  onClick={() => onPick?.(id)}
                  aria-label={`${AGENT[id].name}: ${AGENT[id].does}. ${figure(id)}${live ? ". Working now" : ""}`}>
            <span className="pad-glyph">{AGENT[id].glyph}</span>
            <span className="pad-text">
              <span className="pad-name">{AGENT[id].short}</span>
              <span className="pad-model">{model(id)}</span>
              <span className="orbit-fig">{live ? "working now" : figure(id)}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
