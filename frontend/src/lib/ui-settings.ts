import { useSyncExternalStore } from "react";

import { THEME_COLORS, UI_SETTINGS_STORAGE_KEY as STORAGE_KEY } from "@/config/constants";

/** Per-device display preferences, kept in localStorage. */
export interface UiSettings {
  theme: "system" | "light" | "dark";
  density: "comfortable" | "compact";
  timeFormat: "relative" | "clock";
  defaultView: "active" | "all";
  /** How far back finished jobs are listed in the "All" view. */
  historyHours: 6 | 24 | 48;
  showSparklines: boolean;
  /** Chart options, TensorBoard-style. Smoothing is an EMA weight, 0..0.99. */
  chartSmoothing: number;
  chartLogScale: boolean;
  chartXAxis: "step" | "time";
}

export const UI_DEFAULTS: UiSettings = {
  theme: "system",
  density: "comfortable",
  timeFormat: "relative",
  defaultView: "active",
  historyHours: 48,
  showSparklines: true,
  chartSmoothing: 0.6,
  chartLogScale: false,
  chartXAxis: "step",
};

const listeners = new Set<() => void>();
let current = load();

function load(): UiSettings {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<UiSettings>;
    return { ...UI_DEFAULTS, ...stored };
  } catch {
    return UI_DEFAULTS; // private mode or corrupt value
  }
}

export function updateUiSettings(patch: Partial<UiSettings>): void {
  current = { ...current, ...patch };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
  } catch {
    // Not persisted; still applies for this session.
  }
  applyUiSettings(current);
  listeners.forEach((notify) => notify());
}

export function useUiSettings(): UiSettings {
  return useSyncExternalStore(
    (notify) => {
      listeners.add(notify);
      return () => listeners.delete(notify);
    },
    () => current,
  );
}

const systemDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;

export function applyUiSettings(settings: UiSettings): void {
  const theme = settings.theme === "system" ? (systemDark() ? "dark" : "light") : settings.theme;
  const root = document.documentElement;
  root.dataset["theme"] = theme;
  root.dataset["density"] = settings.density;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLORS[theme]);
}

/** Apply now, and follow the OS when the theme is "system". */
export function initUiSettings(): void {
  applyUiSettings(current);
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => current.theme === "system" && applyUiSettings(current));
}
