import { defineConfig, devices } from "@playwright/test";

// Runs against a running stack: make up (console on :8080) by default, or E2E_BASE_URL.
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        // System Chrome by default (no browser download); E2E_CHROME points at another Chromium binary.
        ...(process.env.E2E_CHROME ? { launchOptions: { executablePath: process.env.E2E_CHROME } } : { channel: "chrome" }),
      } }],
});
