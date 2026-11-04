// Mirrors backend/src/pulse/schemas.py. Keep both in sync.

export type JobState = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED" | "TIMEOUT";

export type EventKind =
  | "job_started"
  | "job_completed"
  | "job_failed"
  | "job_cancelled"
  | "job_time_limit"
  | "job_stalled";

/** "direct": Pulse polls over SSH. "agent": a script on the login node reports in. */
export type Connection = "direct" | "agent";

export interface Account {
  id: number;
  cluster: string;
  username: string;
  host: string;
  port: number;
  color: number;
  notify: boolean;
  connection: Connection;
  last_polled_at: string | null;
  last_error: string | null;
}

export interface AccountCreate {
  /** Omit to let the server derive it from the host. */
  cluster?: string;
  username: string;
  host: string;
  port?: number;
  notify?: boolean;
  connection?: Connection;
}

export type AccountUpdate = Partial<Pick<Account, "cluster" | "notify">>;

export interface AccountCheck {
  ok: boolean;
  error: string | null;
}

export interface Job {
  id: number;
  account_id: number;
  slurm_id: string;
  name: string;
  partition: string;
  state: JobState;
  reason: string | null;
  nodes: number;
  gpus: number;
  node_list: string | null;
  submit_time: string | null;
  start_time: string | null;
  end_time: string | null;
  time_limit_s: number | null;
  elapsed_s: number;
  exit_code: number | null;
  epoch: string | null;
  last_loss: number | null;
  gpu_util: number | null;
  gpu_mem: number | null;
  loss_trend: number[];
  time_used: number | null;
}

export interface MetricPoint {
  t: string;
  v: number;
}

export interface JobDetail extends Job {
  log_tail: string[];
  log_updated_at: string | null;
  series: Partial<Record<"loss" | "gpu_util" | "gpu_mem", MetricPoint[]>>;
}

export interface PulseEvent {
  id: number;
  account_id: number;
  job_id: number | null;
  kind: EventKind;
  message: string;
  created_at: string;
}

export interface Preferences {
  alerts: Record<EventKind, boolean>;
}

export interface SetupInfo {
  slurm_backend: "mock" | "ssh";
  /** Key users authorise on their cluster; null in demo (mock) mode. */
  ssh_public_key: string | null;
}

/** Message on the /api/stream Server-Sent Events channel. */
export interface LiveUpdate {
  type: "update";
  accounts: number[];
  events: PulseEvent[];
}

export interface PushConfig {
  enabled: boolean;
  public_key: string | null;
}

export interface PushSubscriptionJSON {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}
