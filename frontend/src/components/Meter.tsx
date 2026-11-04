import { cn } from "@/lib/utils";

/** Thin horizontal bar for a 0..1 fraction. */
export function Meter({ value, className }: { value: number | null; className?: string }) {
  const pct = Math.round(Math.min(1, Math.max(0, value ?? 0)) * 100);
  return (
    <div
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className={cn("h-1 w-full overflow-hidden rounded-full bg-muted", className)}
    >
      <div className="h-full rounded-full bg-foreground/80" style={{ width: `${pct}%` }} />
    </div>
  );
}
