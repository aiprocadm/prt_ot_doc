import { expect, test } from "@playwright/test";

/**
 * Минимальный smoke-контур регрессии.
 *
 * Локально:
 * - `E2E_START_SERVER=1 npm run e2e` — по умолчанию поднимается **Vite dev** (стабильнее с PWA).
 * - `E2E_PREVIEW=1 E2E_START_SERVER=1 npm run e2e` — **production build + preview** (проверка prod-бандла; не смешивать с block SW без доработок PWA).
 * - Полный логин: `E2E_BASE_URL` на работающий стек + `E2E_USER_EMAIL` / `E2E_USER_PASSWORD` / опционально `E2E_TENANT`.
 */
const serverConfigured = Boolean(process.env.E2E_BASE_URL || process.env.E2E_START_SERVER === "1");

test.describe("smoke", () => {
  test.skip(!serverConfigured, "Set E2E_BASE_URL or E2E_START_SERVER=1");

  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
    await context.addInitScript(() => {
      try {
        localStorage.clear();
        sessionStorage.clear();
      } catch {
        /* ignore */
      }
    });
  });

  test("login page renders", async ({ page }) => {
    await page.goto("/auth/login", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Вход в платформу" })).toBeVisible();
    await expect(page.getByLabel("Tenant")).toBeVisible();
    await expect(page.getByLabel("E-mail")).toBeVisible();
    await expect(page.getByLabel("Пароль")).toBeVisible();
  });

  test("protected route redirects to login when logged out", async ({ page }) => {
    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 30_000 });
  });

  test("login happy path", async ({ page }) => {
    test.skip(
      !process.env.E2E_USER_EMAIL || !process.env.E2E_USER_PASSWORD,
      "Set E2E_USER_EMAIL and E2E_USER_PASSWORD for full login"
    );
    const tenant = process.env.E2E_TENANT ?? "demo";
    await page.goto("/auth/login", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Tenant").fill(tenant);
    await page.getByLabel("E-mail").fill(process.env.E2E_USER_EMAIL!);
    await page.getByLabel("Пароль").fill(process.env.E2E_USER_PASSWORD!);
    await page.getByRole("button", { name: "Войти" }).click();
    await expect(page).not.toHaveURL(/\/auth\/login/, { timeout: 45_000 });
  });
});
