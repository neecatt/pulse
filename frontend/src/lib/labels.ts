import type { EventKind, JobState } from "@/api/types";

/** Text colour per job state; colour is reserved for state and account identity. */
export const stateTone: Record<JobState, string> = {
  RUNNING: "text-run",
  PENDING: "text-pend",
  COMPLETED: "text-muted-foreground",
  FAILED: "text-fail",
  TIMEOUT: "text-fail",
  CANCELLED: "text-muted-foreground",
};

export const EVENT_LABELS: Record<EventKind, string> = {
  job_started: "Job started",
  job_completed: "Job completed",
  job_failed: "Job failed",
  job_cancelled: "Job cancelled",
  job_time_limit: "Near time limit",
  job_stalled: "Training stalled",
};

export const EVENT_STATE: Record<EventKind, JobState> = {
  job_started: "RUNNING",
  job_completed: "COMPLETED",
  job_failed: "FAILED",
  job_cancelled: "CANCELLED",
  job_time_limit: "PENDING",
  job_stalled: "FAILED",
};

/** Distinct colours for runs shown together (compare view). */
export const RUN_COLORS = [
  "var(--acc-0)",
  "var(--acc-1)",
  "var(--acc-2)",
  "var(--acc-3)",
  "var(--acc-4)",
  "var(--acc-5)",
];

export const MAX_COMPARE = RUN_COLORS.length;
