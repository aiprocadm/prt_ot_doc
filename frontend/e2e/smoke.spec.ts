import { expect, test, type Page } from "@playwright/test";
import { loginDefaultUser, loginLimitedUser } from "./helpers/auth";

/**
 * Минимальный smoke-контур регрессии.
 *
 * Локально:
 * - `E2E_START_SERVER=1 npm run e2e` — по умолчанию поднимается **Vite dev** (стабильнее с PWA).
 * - `E2E_PREVIEW=1 E2E_START_SERVER=1 npm run e2e` — **production build + preview** (проверка prod-бандла; не смешивать с block SW без доработок PWA).
 * - Полный логин: `E2E_BASE_URL` на работающий стек + `E2E_USER_EMAIL` / `E2E_USER_PASSWORD` / опционально `E2E_TENANT`.
 */
const serverConfigured = Boolean(process.env.E2E_BASE_URL || process.env.E2E_START_SERVER === "1");
const hasDefaultCreds = Boolean(process.env.E2E_USER_EMAIL && process.env.E2E_USER_PASSWORD);
const hasLimitedCreds = Boolean(process.env.E2E_LIMITED_USER_EMAIL && process.env.E2E_LIMITED_USER_PASSWORD);

const waitMainShellReady = async (page: Page) => {
  await expect(page.getByText("Единый контур ОТ/ПБ")).toBeVisible({ timeout: 30_000 });
};

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

  test.describe("mandatory (no external creds)", () => {
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

    test("attention hub route redirects to login when logged out", async ({ page }) => {
      await page.goto("/workspace/attention", { waitUntil: "domcontentloaded" });
      await expect(page).toHaveURL(/\/auth\/login/, { timeout: 30_000 });
    });

    test("unauthorized/denied route shows access denied page", async ({ page }) => {
      await page.goto("/no-access", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "Доступ ограничен" })).toBeVisible();
    });
  });

  test.describe("credential-based flows", () => {
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
      test.skip(!hasDefaultCreds, "Set E2E_USER_EMAIL and E2E_USER_PASSWORD for full login");
      await loginDefaultUser(page);
      await waitMainShellReady(page);
    });

    /** REGRESSION_TEST_MATRIX.md — R11 (шаг 2: список документов после логина). */
    test("R11 documents list after login", async ({ page }) => {
      test.skip(!hasDefaultCreds, "Set E2E_USER_EMAIL and E2E_USER_PASSWORD");
      await loginDefaultUser(page);
      await waitMainShellReady(page);

      await page.goto("/documents", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "Документы" })).toBeVisible({ timeout: 30_000 });

      const nameCellButton = page.locator("table tbody tr").first().getByRole("button").first();
      if ((await nameCellButton.count()) > 0) {
        await nameCellButton.click();
        await expect(page.getByRole("tab", { name: "Предпросмотр" })).toBeVisible({ timeout: 15_000 });
      }
    });

    /** После логина список документов выходит из начального loading (store list / polling). */
    test("R11b documents loading screen settles", async ({ page }) => {
      test.skip(!hasDefaultCreds, "Set E2E_USER_EMAIL and E2E_USER_PASSWORD");
      await loginDefaultUser(page);
      await waitMainShellReady(page);

      await page.goto("/documents", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "Документы" })).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText("Загрузка документов")).toBeHidden({ timeout: 35_000 });
    });

    test("navigation regression: command bar, top nav links and breadcrumb", async ({ page }) => {
      test.skip(!hasDefaultCreds, "Set E2E_USER_EMAIL and E2E_USER_PASSWORD");
      await loginDefaultUser(page);
      await waitMainShellReady(page);

      await page.getByRole("button", { name: "Открыть палитру команд" }).click();
      await page.getByPlaceholder("Найти раздел по названию или группе").fill("Документы");
      await page.getByRole("link", { name: "Документы" }).first().click();
      await expect(page).toHaveURL(/\/documents/);

      await page.getByRole("link", { name: "Единый реестр задач" }).click();
      await expect(page).toHaveURL(/\/tasks/);
      await page.getByRole("link", { name: "Уведомления" }).click();
      await expect(page).toHaveURL(/\/notifications/);

      await page.goto("/documents", { waitUntil: "domcontentloaded" });
      await page.getByRole("link", { name: "Главная" }).click();
      await expect(page).toHaveURL(/\/dashboard/);
    });

    test("navigation regression: mobile menu opens and routes", async ({ page }) => {
      test.skip(!hasDefaultCreds, "Set E2E_USER_EMAIL and E2E_USER_PASSWORD");
      await loginDefaultUser(page);
      await waitMainShellReady(page);

      await page.setViewportSize({ width: 390, height: 844 });
      await page.getByRole("button", { name: "Открыть меню разделов" }).click();
      await page.getByRole("link", { name: "Документы" }).first().click();
      await expect(page).toHaveURL(/\/documents/);
    });

    test("logout returns to login", async ({ page }) => {
      test.skip(!hasDefaultCreds, "Set E2E_USER_EMAIL and E2E_USER_PASSWORD");
      await loginDefaultUser(page);
      await waitMainShellReady(page);

      const profileTrigger = page.getByTestId("user-menu-trigger");
      await expect(profileTrigger).toBeVisible({ timeout: 20_000 });
      await profileTrigger.click();
      await page.getByRole("menuitem", { name: /Выйти/i }).click();
      await expect(page).toHaveURL(/\/auth\/login/, { timeout: 30_000 });
    });

    /** REGRESSION_TEST_MATRIX.md — R12 (нет DOCUMENT_VIEW → AccessDenied). */
    test("R12 limited user denied on documents route", async ({ page }) => {
      test.skip(!hasLimitedCreds, "Set E2E_LIMITED_USER_EMAIL and E2E_LIMITED_USER_PASSWORD (роль без DOCUMENT_VIEW)");
      await loginLimitedUser(page);
      await waitMainShellReady(page);

      await page.goto("/documents", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "Доступ ограничен" })).toBeVisible({ timeout: 30_000 });
    });

    test("limited user denied on attention hub when dashboard permission is missing", async ({ page }) => {
      test.skip(!hasLimitedCreds, "Set E2E_LIMITED_USER_EMAIL and E2E_LIMITED_USER_PASSWORD");
      await loginLimitedUser(page);
      await waitMainShellReady(page);

      await page.goto("/workspace/attention", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "Доступ ограничен" })).toBeVisible({ timeout: 30_000 });
    });
  });
});
