import type { EventKind, JobState } from "@/api/types";

/** Text colour per job state; colour is reserved for state and account identity. */
export const stateTone: Record<JobState, string> = {
  RUNNING: "text-run",
  PENDING: "text-pend",
  COMPLETED: "text-muted-foreground",
  FAILED: "text-fail",
  // Running until the time limit is often the plan, so it isn't shown as a failure.
  TIMEOUT: "text-muted-foreground",
  CANCELLED: "text-muted-foreground",
};

/** How a state reads in badges; Slurm's "TIMEOUT" sounds like an error. */
export const STATE_LABELS: Record<JobState, string> = {
  RUNNING: "RUNNING",
  PENDING: "PENDING",
  COMPLETED: "COMPLETED",
  FAILED: "FAILED",
  TIMEOUT: "TIME LIMIT",
  CANCELLED: "CANCELLED",
};

export const EVENT_LABELS: Record<EventKind, string> = {
  job_started: "Job started",
  job_completed: "Job completed",
  job_timed_out: "Reached time limit",
  job_failed: "Job failed",
  job_cancelled: "Job cancelled",
  job_time_limit: "Near time limit",
  job_stalled: "Training stalled",
  job_nan: "Loss became NaN",
  job_diverging: "Loss diverging",
  job_plateau: "Loss plateaued",
};

export const EVENT_STATE: Record<EventKind, JobState> = {
  job_started: "RUNNING",
  job_completed: "COMPLETED",
  job_timed_out: "TIMEOUT",
  job_failed: "FAILED",
  job_cancelled: "CANCELLED",
  job_time_limit: "PENDING",
  job_stalled: "FAILED",
  job_nan: "FAILED",
  job_diverging: "FAILED",
  job_plateau: "PENDING",
};
