import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 70000,
  workers: 1,
  use: {
    baseURL: process.env.DURABLE_UI_URL || "http://127.0.0.1:5173",
    channel: process.env.PLAYWRIGHT_CHANNEL || "chromium",
    viewport: { width: 1440, height: 950 },
  },
});
