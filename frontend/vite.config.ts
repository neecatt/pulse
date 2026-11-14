import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env["PULSE_API_PROXY"] ?? "http://localhost:8000";

  return {
    // The router plugin must run before the React plugin.
    plugins: [tanstackRouter({ target: "react", autoCodeSplitting: true }), react(), tailwindcss()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      port: 5173,
      // The public docs pages render the repository's docs/*.md.
      fs: { allow: [".", "../docs"] },
      proxy: { "/api": { target: apiTarget, changeOrigin: true } },
    },
  };
});
