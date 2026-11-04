// Mirrors backend/src/pulse/schemas.py. Keep both in sync.

export type JobState = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED" | "TIMEOUT";

export type EventKind =
  | "job_started"
  | "job_completed"
  | "job_failed"
  | "job_cancelled"
  | "job_time_limit"
  | "job_stalled"
  | "job_nan"
  | "job_diverging"
  | "job_plateau";

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
  /** Metric shown as "Loss" and in sparklines, e.g. "loss" or "train/loss". */
  primary_metric: string | null;
  tags: string[];
  /** Job array (sweep) this task belongs to, e.g. "123" for "123_4". */
  array_id: string | null;
  time_used: number | null;
}

export interface MetricPoint {
  t: string;
  v: number;
}

export type HparamValue = string | number | boolean | null;

export interface NodeStats {
  cpu: number | null;
  mem: number | null;
  gpus: { util: number; mem: number }[];
}

export interface MetricStats {
  last: number;
  min: number;
  max: number;
}

/** A job as a row of the runs table. */
export interface Run extends Job {
  hparams: Record<string, HparamValue>;
  metric_stats: Record<string, MetricStats>;
}

export interface JobDetail extends Job {
  log_tail: string[];
  log_updated_at: string | null;
  note: string | null;
  hparams: Record<string, HparamValue>;
  /** Latest usage per node. */
  node_stats: Record<string, NodeStats>;
  /** System metrics: gpu_util, gpu_mem and per node sys/<node>/{cpu,mem,gpu,gpu_mem}. */
  series: Record<string, MetricPoint[]>;
}

export interface JobUpdate {
  note?: string;
  tags?: string[];
}

/** A training-metric sample: step (if known), time, value. */
export interface StepPoint {
  s: number | null;
  t: string;
  v: number;
}

export interface JobMetrics {
  metrics: Record<string, StepPoint[]>;
  primary: string | null;
  hparams: Record<string, HparamValue>;
  files: string[];
}

export interface PulseEvent {
  id: number;
  account_id: number;
  job_id: number | null;
  kind: EventKind;
  message: string;
  created_at: string;
}

export interface Monitoring {
  live_refresh_seconds: number;
  idle_refresh_seconds: number;
  stall_minutes: number;
  time_limit_warning_percent: number;
  diverge_percent: number;
  plateau_minutes: number;
}

export interface Preferences {
  alerts: Record<EventKind, boolean>;
  monitoring: Monitoring;
}

export interface PreferencesUpdate {
  alerts?: Partial<Record<EventKind, boolean>>;
  monitoring?: Partial<Monitoring>;
}

export interface Health {
  status: string;
  version: string;
  slurm_backend: "mock" | "ssh";
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

// Auth

export interface Me {
  id: number;
  username: string;
  is_admin: boolean;
  /** The password is set by PULSE_ADMIN_PASSWORD and can't be changed in the app. */
  password_from_env: boolean;
}

export interface AuthStatus {
  setup_required: boolean;
  signup_allowed: boolean;
  /** Who this browser is signed in as; null when signed out. */
  user: Me | null;
}

export interface Credentials {
  username: string;
  password: string;
  /** First-run setup only: the one-time code printed in the server log. */
  setup_code?: string;
}

export interface LoginSession {
  id: number;
  user_agent: string | null;
  created_at: string;
  last_seen_at: string;
  current: boolean;
}
