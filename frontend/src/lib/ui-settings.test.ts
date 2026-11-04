import { afterEach, describe, expect, it, vi } from "vitest";

import { UI_SETTINGS_STORAGE_KEY as STORAGE_KEY } from "@/config/constants";

import { UI_DEFAULTS } from "./ui-settings";

async function freshModule() {
  vi.resetModules();
  return import("./ui-settings");
}

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset["theme"];
});

describe("ui settings", () => {
  it("starts from defaults", async () => {
    const { applyUiSettings } = await freshModule();
    applyUiSettings(UI_DEFAULTS);
    expect(document.documentElement.dataset["theme"]).toBe("light"); // matchMedia mock: light
    expect(document.documentElement.dataset["density"]).toBe("comfortable");
  });

  it("persists and applies updates", async () => {
    const { updateUiSettings } = await freshModule();
    updateUiSettings({ theme: "dark", density: "compact" });

    expect(document.documentElement.dataset["theme"]).toBe("dark");
    expect(document.documentElement.dataset["density"]).toBe("compact");
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}")).toMatchObject({
      theme: "dark",
      density: "compact",
      historyHours: 48,
    });
  });

  it("loads saved values and ignores corrupt storage", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ timeFormat: "clock" }));
    const { updateUiSettings } = await freshModule();
    updateUiSettings({});
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}").timeFormat).toBe("clock");

    localStorage.setItem(STORAGE_KEY, "{not json");
    const again = await freshModule();
    again.updateUiSettings({});
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}").timeFormat).toBe("relative");
  });
});
