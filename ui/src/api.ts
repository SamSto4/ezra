// Thin client for the local Ezra API (src/ezra/api.py). The UI holds no logic of its own.

export type Verdict = "PASS" | "REVISE" | "HOLD" | "ESCALATE";

export interface Status {
  spent_today_usd: number;
  daily_limit_usd: number;
  task_limit_usd: number;
  pending_approvals: number;
  last_event_id: number;
  running: string[];
}

export interface Job {
  task_id: string;
  action: string;
  state: "running" | "finished" | "failed";
  outcome: string | null;
  error: string | null;
}

export interface TaskSummary {
  task_id: string;
  created_at: string;
  status: string;
  description: string;
  title: string | null;
  spend_usd: number;
  verdict: Verdict | null;
  job: Job | null;
}

export interface Criterion {
  id: string;
  text: string;
  severity: string;
  verification: string;
}

export interface Invocation {
  invocation_id: string;
  operation_id: string;
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  actual_cost_usd: number | null;
  latency_ms: number;
  prompt_version: string;
  context: { label: string; chars: number; sha: string }[];
  response_hash: string | null;
}

export interface TraceRow {
  at: string;
  step: string;
  kind: string;
  detail: string;
  data: Record<string, unknown>;
  invocation: Invocation | null;
}

export interface Review {
  verdict: Verdict;
  matched_rule: number;
  tier: string;
  summary: string;
  criteria_results: { criterion_id: string; status: string; evidence: string }[];
  findings: { severity: string; code: string; message: string }[];
  required_corrections: string[];
}

export interface AgentInfo {
  id: string;
  name: string;
  department: string;
  role: string;
  can: string[];
  cannot: string[];
  operations: { operation: string; model: string; effort: string; calls: number;
                cost_usd: number; latency_ms: number; prompt_versions: string[] }[];
  calls: number;
  cost_usd: number;
  cache_share: number;
  last_at: string | null;
  tasks: number;
  verdicts?: Record<string, number>;
  tier1_only?: number;
  plans?: number;
  adjudications?: number;
  runs?: number;
  revisions?: number;
  routed?: number;
  lessons_active?: number;
  lessons_total?: number;
  learned_from?: number;
  memory?: string;
}

export interface Lesson {
  lesson_id: string;
  operation: string;
  project: string | null;
  kind: "strategy" | "pitfall" | "check";
  trigger: string;
  text: string;
  evidence: string[];
  source: string;
  status: "active" | "retired";
  helpful: number;
  harmful: number;
  uses: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SystemInfo {
  routing_version: string;
  routing: { operation: string; model: string; effort: string; agent: string | null }[];
  limits: Record<string, number>;
  prices: Record<string, { input: number; output: number; cache_read: number; cache_write: number }>;
  verdict_rules: { rule: number; verdict: string; when: string }[];
  decisions: { id: string; title: string; status: string }[];
  cache_saved_usd: number;
  config_dir: string;
}

export interface Approval {
  approval_id: string;
  task_id: string | null;
  kind: string;
  status: string;
  summary: string;
  created_at: string;
}

export interface TaskDetail {
  task: { task_id: string; description: string; acceptance_criteria: Criterion[];
          constraints: string[]; budget: { task_limit_usd: number } };
  status: string;
  title: string | null;
  verdict: Verdict | null;
  spend_usd: number;
  calls: number;
  rows: TraceRow[];
  totals: { operation: string; calls: number; input_tokens: number; output_tokens: number;
            cache_read_tokens: number; cache_creation_tokens: number; cost_usd: number;
            latency_ms: number }[];
  reviews: Review[];
  approvals: Approval[];
  job: Job | null;
}

export interface AskResult {
  route: "direct" | "code" | "unsupported";
  answer: string | null;
  unsupported_reason: string | null;
  title: string | null;
  task: { task_id: string; description: string; acceptance_criteria: Criterion[] } | null;
  cost_usd: number;
}

export interface EzraEvent {
  id: number;
  task_id: string | null;
  at: string;
  kind: string;
  data: Record<string, unknown>;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    // Required on every write: other websites can't send it (see api.py).
    headers: { "Content-Type": "application/json", "X-Ezra-Client": "ui", ...init?.headers },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = body.detail;
    throw new Error(typeof d === "string" ? d : d?.hold?.summary ?? `HTTP ${res.status}`);
  }
  return body as T;
}

const post = <T>(path: string, body?: unknown) =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  status: () => call<Status>("/api/status"),
  tasks: () => call<TaskSummary[]>("/api/tasks"),
  task: (id: string) => call<TaskDetail>(`/api/tasks/${id}`),
  text: (sha: string) => call<{ text: string }>(`/api/texts/${sha}`),
  approvals: () => call<Approval[]>("/api/approvals"),
  agents: () => call<AgentInfo[]>("/api/agents"),
  system: () => call<SystemInfo>("/api/system"),
  diff: (id: string) => call<{ branch: string; diff: string; truncated?: boolean; note?: string }>(`/api/tasks/${id}/diff`),
  ask: (request: string) => post<AskResult>("/api/ask", { request }),
  run: (id: string, cap?: number, memory?: string) =>
    post<Job>(`/api/tasks/${id}/run`, cap || memory ? { task_budget_usd: cap ?? null, memory: memory ?? null } : undefined),
  learn: (id: string) => post<Job>(`/api/tasks/${id}/learn`),
  lessons: () => call<Lesson[]>("/api/lessons"),
  retireLesson: (id: string) => post<Lesson>(`/api/lessons/${id}/retire`),
  resume: (id: string) => post<Job>(`/api/tasks/${id}/resume`),
  review: (id: string) => post<Job>(`/api/tasks/${id}/review`),
  abandon: (id: string) => post<unknown>(`/api/tasks/${id}/abandon`),
  answer: (approvalId: string, approved: boolean, extendUsd?: number) =>
    post<Job>(`/api/approvals/${approvalId}`, { approved, extend_usd: extendUsd ?? null }),
};

/** Live events from the server (SSE). Returns a function that closes the stream. */
export function subscribe(onEvent: (e: EzraEvent) => void, after = 0): () => void {
  const src = new EventSource(`/api/events/stream?after=${after}`);
  src.onmessage = (m) => onEvent(JSON.parse(m.data));
  return () => src.close();
}

export const usd = (n: number | null | undefined, digits = 4) =>
  n == null ? "—" : `$${n.toFixed(digits)}`;
