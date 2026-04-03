import { defineConfig } from "@playwright/test";

const startServer = process.env.E2E_START_SERVER === "1";
const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:4173";
/** По умолчанию dev-сервер: в DEV `registerPwa` снимает SW и нет white-screen при block SW. Для регрессии prod-сборки: E2E_PREVIEW=1. */
const usePreview = process.env.E2E_PREVIEW === "1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  timeout: 60_000,
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    serviceWorkers: usePreview ? "allow" : "block"
  },
  webServer: startServer
    ? {
        command: usePreview
          ? "npm run build && npm run preview -- --host 127.0.0.1 --port 4173"
          : "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort",
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: usePreview ? 180_000 : 120_000
      }
    : undefined
});
