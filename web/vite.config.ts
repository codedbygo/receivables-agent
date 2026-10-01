import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The dev server proxies the API so the browser talks to one origin, as it does behind nginx.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  preview: { port: 4173, proxy: { "/api": { target: "http://127.0.0.1:8000", timeout: 90_000 } } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
