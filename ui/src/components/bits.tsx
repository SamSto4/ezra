import { useRef, type CSSProperties, type ReactNode } from "react";
import type { Verdict } from "../api";

export function Star({ size = 28 }: { size?: number }) {
  // Ezra's four-point star mark.
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="star">
      <defs>
        <linearGradient id="starg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#b9d2ff" />
          <stop offset="1" stopColor="#5b84ff" />
        </linearGradient>
      </defs>
      <path d="M16 1 C17 11 21 15 31 16 C21 17 17 21 16 31 C15 21 11 17 1 16 C11 15 15 11 16 1 Z"
            fill="url(#starg)" />
    </svg>
  );
}

const VERDICT_CLASS: Record<string, string> = { PASS: "ok", REVISE: "warn", HOLD: "warn", ESCALATE: "bad" };

export function VerdictBadge({ verdict }: { verdict: Verdict | string | null }) {
  if (!verdict) return <span className="badge">NO VERDICT</span>;
  return <span className={`badge ${VERDICT_CLASS[verdict] ?? ""}`}>{verdict}</span>;
}

const STATUS_CLASS: Record<string, string> = {
  done: "ok", running: "live", held: "warn", in_review: "live", escalated: "bad", failed: "bad",
  created: "",
};

export function StatusDot({ status }: { status: string }) {
  const label = status.replace("_", " ");
  return (
    <span className={`status ${STATUS_CLASS[status] ?? ""}`}>
      <i />{label.charAt(0).toUpperCase() + label.slice(1)}
    </span>
  );
}

export function Eyebrow({ children, dot }: { children: ReactNode; dot?: string }) {
  return <span className="eyebrow" style={dot ? ({ "--dot": dot } as CSSProperties) : undefined}>{children}</span>;
}

export function Meter({ value, max, label, right }:
  { value: number; max: number; label: ReactNode; right?: ReactNode }) {
  const share = Math.max(0, Math.min(1, value / max));
  return (
    <div className="meter">
      <div className="meter-label"><span>{label}</span>{right}</div>
      <div className="meter-track" role="meter" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}>
        <div className={`meter-fill ${share > 0.8 ? "hot" : ""}`} style={{ transform: `scaleX(${share})` }} />
      </div>
    </div>
  );
}

export function Panel({ title, eyebrow, right, children, className = "", id, flat, style, body = true }: {
  title?: ReactNode; eyebrow?: ReactNode; right?: ReactNode; children: ReactNode; className?: string;
  id?: string; flat?: boolean; style?: CSSProperties; body?: boolean;
}) {
  return (
    <section id={id} className={`panel ${className}`} style={style}>
      {(title || right || eyebrow) && (
        <header className={`panel-head ${flat ? "flat" : ""}`}>
          <div>
            {eyebrow && <div style={{ marginBottom: title ? 8 : 0 }}>{eyebrow}</div>}
            {title && <h3 className="section-title">{title}</h3>}
          </div>
          {right}
        </header>
      )}
      {body ? <div className="panel-body">{children}</div> : children}
    </section>
  );
}

export const ago = (iso: string) => {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
};

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });

/** Remembers which keys were already on screen, so only genuinely new rows animate in
 *  (never on every refresh, and never on first load). */
export function useFresh() {
  const seen = useRef<Set<string> | null>(null);
  return (keys: string[]) => {
    const first = seen.current === null;
    const prev = seen.current ?? new Set<string>();
    const fresh = new Set(first ? [] : keys.filter((k) => !prev.has(k)));
    seen.current = new Set(keys);
    return fresh;
  };
}
