const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** 3725 -> "1h 02m"; 59 -> "0m"; 90000 -> "1d 1h". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s >= DAY) return `${Math.floor(s / DAY)}d ${Math.floor((s % DAY) / HOUR)}h`;
  if (s >= HOUR)
    return `${Math.floor(s / HOUR)}h ${String(Math.floor((s % HOUR) / MINUTE)).padStart(2, "0")}m`;
  return `${Math.floor(s / MINUTE)}m`;
}

/** Compact time-ago label: "now", "5m", "3h", "2d". */
export function formatAgo(iso: string, now: number = Date.now()): string {
  const seconds = (now - new Date(iso).getTime()) / 1000;
  if (seconds < MINUTE) return "now";
  if (seconds < HOUR) return `${Math.floor(seconds / MINUTE)}m`;
  if (seconds < DAY) return `${Math.floor(seconds / HOUR)}h`;
  return `${Math.floor(seconds / DAY)}d`;
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatNumber(value: number | null, digits = 3): string {
  return value === null ? "—" : Number(value.toPrecision(digits)).toString();
}

export function formatPercent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value)}%`;
}
