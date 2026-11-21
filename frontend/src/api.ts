import { useQuery } from "@tanstack/react-query";

export type Json = Record<string, unknown>;
export type StepSpec = {
  key: string;
  name: string;
  task_type: string;
  config: Json;
  retry: {
    max_attempts: number;
    delay_seconds: number;
    max_delay_seconds: number;
  };
  timeout_seconds: number;
};
export type Definition = {
  name: string;
  description: string;
  steps: StepSpec[];
};
export type Workflow = {
  id: string;
  name: string;
  description: string;
  workflow_key: string;
  status: string;
  draft: Definition;
  latest_version: number;
  run_count: number;
  created_at: string;
};
export type Version = { id: string; version: number; definition: Definition };
export type Run = {
  id: string;
  workflow_id: string;
  workflow_name: string;
  version: number;
  status: string;
  input_data: Json;
  output_data: Json | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  step_count: number;
};
export type Step = {
  id: string;
  workflow_run_id: string;
  key: string;
  name: string;
  task_type: string;
  status: string;
  input_data: Json;
  output_data: Json | null;
  error_message: string | null;
  attempt_count: number;
  max_attempts: number;
  worker_id: string | null;
  lease_owner: string | null;
  started_at: string | null;
  completed_at: string | null;
};
export type Attempt = {
  id: string;
  step_execution_id: string;
  attempt_number: number;
  worker_id: string;
  status: string;
  duration_ms: number | null;
  error_message: string | null;
  started_at: string;
  input_data: Json;
  output_data: Json | null;
};
export type EventRow = {
  id: string;
  event_type: string;
  message: string;
  sequence: number;
  created_at: string;
  workflow_run_id: string | null;
  metadata: Json;
};
export type Worker = {
  id: string;
  worker_name: string;
  hostname: string;
  status: string;
  current_task_id: string | null;
  execution_count: number;
  last_heartbeat_at: string;
};
export type Health = {
  api: string;
  postgres: string;
  redis: string;
  workers: string;
  queue: Record<string, number>;
  version: string;
  environment: string;
};
export type Bucket = {
  hour: string;
  completed: number;
  failed: number;
  started: number;
};
export type Stats = {
  total_workflows: number;
  total_runs: number;
  running_runs: number;
  completed_runs: number;
  failed_runs: number;
  active_workers: number;
  pending_tasks: number;
  running_tasks: number;
  activity: Bucket[];
};
export type TaskInfo = {
  task_type: string;
  description: string;
  config_schema: Json;
};
export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
export type Timeline = { run: Run; steps: Step[]; events: Page<EventRow> };
export const BASE = import.meta.env.VITE_API_BASE || "/api/v1";

export async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(BASE + path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (HTTP ${response.status})`,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function params(data: Record<string, string | number | undefined>) {
  const p = new URLSearchParams();
  Object.entries(data).forEach(([k, v]) => {
    if (v !== undefined && v !== "") p.set(k, String(v));
  });
  return "?" + p.toString();
}
export function useApi<T>(
  path: string,
  poll: number | false = false,
  enabled = true,
) {
  return useQuery<T>({
    queryKey: [path],
    queryFn: () => request<T>(path),
    refetchInterval: poll,
    enabled,
  });
}
export const live = (status: string) =>
  ["RUNNING", "PENDING", "PAUSED"].includes(status);
export const short = (id: string | null) => (id ? id.slice(0, 8) : "—");
export const time = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "—";
export function duration(start: string | null, end: string | null) {
  if (!start) return "—";
  const ms = Math.max(
    0,
    (end ? Date.parse(end) : Date.now()) - Date.parse(start),
  );
  if (ms < 1000) return Math.round(ms) + " ms";
  return ms < 60000
    ? (ms / 1000).toFixed(1) + " s"
    : Math.floor(ms / 60000) + "m " + Math.floor((ms / 1000) % 60) + "s";
}
