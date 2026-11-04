/**
 * Fixed limits and contracts shared across the frontend. Deployment settings
 * live in config/env.ts; per-device preferences in lib/ui-settings.ts.
 */

// Time units
export const SECOND_MS = 1000;
export const MINUTE_MS = 60 * SECOND_MS;
export const HOUR_MS = 60 * MINUTE_MS;
export const DAY_MS = 24 * HOUR_MS;

// Data refresh. Live data arrives over /api/stream; this is only the fallback
// for when the stream is down.
export const FALLBACK_REFRESH_MS = MINUTE_MS;
export const DEFAULT_STALE_MS = 5 * SECOND_MS;

// Account colours: one Tailwind class per token in styles.css. The length must
// match ACCOUNT_PALETTE_SIZE in backend/src/pulse/constants.py.
export const ACCOUNT_COLOR_CLASSES = [
  "bg-acc-0",
  "bg-acc-1",
  "bg-acc-2",
  "bg-acc-3",
  "bg-acc-4",
  "bg-acc-5",
] as const;

// Runs shown together (compare view) get distinct colours.
export const RUN_COLORS = [
  "var(--acc-0)",
  "var(--acc-1)",
  "var(--acc-2)",
  "var(--acc-3)",
  "var(--acc-4)",
  "var(--acc-5)",
] as const;
export const MAX_COMPARE = RUN_COLORS.length;

// Per-device settings storage; keep in sync with the pre-paint script in index.html.
export const UI_SETTINGS_STORAGE_KEY = "pulse.ui";
export const THEME_COLORS = { light: "#fcfcfc", dark: "#0e0f10" } as const;

// Feedback timing
export const COPIED_FEEDBACK_MS = 1500;
