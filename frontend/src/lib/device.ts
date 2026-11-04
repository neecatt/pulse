/** A short, human name for a browser: "Safari on iPhone", "Chrome on macOS". */
export function describeDevice(userAgent: string | null): string {
  if (!userAgent) return "Unknown device";
  const os = /iPhone|iPad|Android|Mac OS X|Windows|Linux/.exec(userAgent)?.[0] ?? "";
  const browser = /Firefox|Edg|Chrome|Safari/.exec(userAgent)?.[0] ?? "";
  const names: Record<string, string> = { "Mac OS X": "macOS", Edg: "Edge" };
  return [names[browser] ?? browser, names[os] ?? os].filter(Boolean).join(" on ") || userAgent;
}
