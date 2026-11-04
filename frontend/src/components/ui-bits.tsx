import type { JobState } from "@/lib/mock";

const stateClass: Record<JobState, string> = {
  RUNNING: "text-run",
  PENDING: "text-pend",
  COMPLETED: "text-muted-foreground",
  FAILED: "text-fail",
  CANCELLED: "text-muted-foreground",
};

export function StateDot({ state }: { state: JobState }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-[11px] tracking-wider ${stateClass[state]}`}
    >
      <span
        className={`size-1.5 rounded-full bg-current ${state === "RUNNING" ? "animate-pulse" : ""}`}
      />
      {state}
    </span>
  );
}

export function Spark({ data, className = "" }: { data: number[]; className?: string }) {
  if (data.length < 2) return <div className={`h-10 ${className}`} />;
  const max = Math.max(...data),
    min = Math.min(...data);
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * 100},${36 - ((v - min) / (max - min || 1)) * 32}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className={`h-10 w-full ${className}`}>
      <polyline
        points={pts}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function Bar({ value }: { value: number }) {
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
      <div className="h-full bg-foreground" style={{ width: `${value * 100}%` }} />
    </div>
  );
}
