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
