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

  /**
   * Неверный пароль → сообщение под полем пароля (docs/stabilization/TEST_COVERAGE_GAPS.md).
   * Нужен только E2E_USER_EMAIL (тот же tenant, что и для happy path).
   */
  test("login wrong password shows inline error", async ({ page }) => {
    test.skip(!process.env.E2E_USER_EMAIL, "Set E2E_USER_EMAIL (password may be wrong on purpose)");
    const tenant = process.env.E2E_TENANT ?? "demo";
    await page.goto("/auth/login", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Tenant").fill(tenant);
    await page.getByLabel("E-mail").fill(process.env.E2E_USER_EMAIL!);
    await page.getByLabel("Пароль").fill("__e2e_wrong_password__");
    await page.getByRole("button", { name: "Войти" }).click();
    await expect(page.locator("form p.text-destructive").first()).toBeVisible({ timeout: 20_000 });
    await expect(page).toHaveURL(/\/auth\/login/);
  });

  /** REGRESSION_TEST_MATRIX.md — R11 (шаг 1: вход с tenant). */
  test("R11 login happy path", async ({ page }) => {
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

  /** REGRESSION_TEST_MATRIX.md — R11 (шаг 2: список документов после логина). */
  test("R11 documents list after login", async ({ page }) => {
    test.skip(
      !process.env.E2E_USER_EMAIL || !process.env.E2E_USER_PASSWORD,
      "Set E2E_USER_EMAIL and E2E_USER_PASSWORD"
    );
    const tenant = process.env.E2E_TENANT ?? "demo";
    await page.goto("/auth/login", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Tenant").fill(tenant);
    await page.getByLabel("E-mail").fill(process.env.E2E_USER_EMAIL!);
    await page.getByLabel("Пароль").fill(process.env.E2E_USER_PASSWORD!);
    await page.getByRole("button", { name: "Войти" }).click();
    await expect(page).not.toHaveURL(/\/auth\/login/, { timeout: 45_000 });

    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Документы" })).toBeVisible({ timeout: 30_000 });

    const nameCellButton = page.locator("table tbody tr").first().getByRole("button").first();
    if ((await nameCellButton.count()) > 0) {
      await nameCellButton.click();
      await expect(page.getByRole("tab", { name: "Предпросмотр" })).toBeVisible({ timeout: 15_000 });
    }
  });

  test("logout returns to login", async ({ page }) => {
    test.skip(
      !process.env.E2E_USER_EMAIL || !process.env.E2E_USER_PASSWORD,
      "Set E2E_USER_EMAIL and E2E_USER_PASSWORD"
    );
    const tenant = process.env.E2E_TENANT ?? "demo";
    await page.goto("/auth/login", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Tenant").fill(tenant);
    await page.getByLabel("E-mail").fill(process.env.E2E_USER_EMAIL!);
    await page.getByLabel("Пароль").fill(process.env.E2E_USER_PASSWORD!);
    await page.getByRole("button", { name: "Войти" }).click();
    await expect(page).not.toHaveURL(/\/auth\/login/, { timeout: 45_000 });

    const profileTrigger = page.getByTestId("user-menu-trigger");
    await expect(profileTrigger).toBeVisible({ timeout: 20_000 });
    await profileTrigger.click();
    await page.getByRole("menuitem", { name: /Выйти/i }).click();
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 30_000 });
  });

  /** REGRESSION_TEST_MATRIX.md — R12 (нет DOCUMENT_VIEW → AccessDenied). */
  test("R12 limited user denied on documents route", async ({ page }) => {
    test.skip(
      !process.env.E2E_LIMITED_USER_EMAIL || !process.env.E2E_LIMITED_USER_PASSWORD,
      "Set E2E_LIMITED_USER_EMAIL and E2E_LIMITED_USER_PASSWORD (роль без DOCUMENT_VIEW)"
    );
    const tenant = process.env.E2E_TENANT ?? "demo";
    await page.goto("/auth/login", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Tenant").fill(tenant);
    await page.getByLabel("E-mail").fill(process.env.E2E_LIMITED_USER_EMAIL!);
    await page.getByLabel("Пароль").fill(process.env.E2E_LIMITED_USER_PASSWORD!);
    await page.getByRole("button", { name: "Войти" }).click();
    await expect(page).not.toHaveURL(/\/auth\/login/, { timeout: 45_000 });

    await page.goto("/documents", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Доступ ограничен" })).toBeVisible({ timeout: 30_000 });
  });
});
