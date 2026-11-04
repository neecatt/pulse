// Apply the saved theme before first paint to avoid a flash (see src/lib/ui-settings.ts).
try {
  var ui = JSON.parse(localStorage.getItem("pulse.ui") || "{}");
  var theme = ui.theme || "system";
  var dark =
    theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.dataset.density = ui.density || "comfortable";
} catch (e) {}
