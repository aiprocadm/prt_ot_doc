import { expect, test, type Page } from "@playwright/test";

const serverConfigured = Boolean(process.env.E2E_BASE_URL || process.env.E2E_START_SERVER === "1");

const loginAsDefaultUser = async (page: Page) => {
  const tenant = process.env.E2E_TENANT ?? "demo";
  await page.goto("/auth/login", { waitUntil: "domcontentloaded" });
  await page.getByLabel("Tenant").fill(tenant);
  await page.getByLabel("E-mail").fill(process.env.E2E_USER_EMAIL!);
  await page.getByLabel("Пароль").fill(process.env.E2E_USER_PASSWORD!);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page).not.toHaveURL(/\/auth\/login/, { timeout: 45_000 });
};

test.describe("key user scenarios", () => {
  test.skip(!serverConfigured, "Set E2E_BASE_URL or E2E_START_SERVER=1");

  test("create company flow opens from companies page", async ({ page }) => {
    test.skip(
      !process.env.E2E_USER_EMAIL || !process.env.E2E_USER_PASSWORD,
      "Set E2E_USER_EMAIL and E2E_USER_PASSWORD"
    );
    await loginAsDefaultUser(page);

    await page.goto("/companies");
    await expect(page.getByRole("heading", { name: /Компани/i })).toBeVisible();
  });

  test("upload document flow opens document wizard", async ({ page }) => {
    test.skip(
      !process.env.E2E_USER_EMAIL || !process.env.E2E_USER_PASSWORD,
      "Set E2E_USER_EMAIL and E2E_USER_PASSWORD"
    );
    await loginAsDefaultUser(page);

    await page.goto("/documents/wizard");
    await expect(page).toHaveURL(/\/documents\/wizard/);
  });

  test("assign task flow opens task registry", async ({ page }) => {
    test.skip(
      !process.env.E2E_USER_EMAIL || !process.env.E2E_USER_PASSWORD,
      "Set E2E_USER_EMAIL and E2E_USER_PASSWORD"
    );
    await loginAsDefaultUser(page);

    await page.goto("/tasks");
    await expect(page.getByRole("heading", { name: /Задач/i })).toBeVisible();
  });

  test("run inspection flow opens inspections page", async ({ page }) => {
    test.skip(
      !process.env.E2E_USER_EMAIL || !process.env.E2E_USER_PASSWORD,
      "Set E2E_USER_EMAIL and E2E_USER_PASSWORD"
    );
    await loginAsDefaultUser(page);

    await page.goto("/inspections");
    await expect(page.getByRole("heading", { name: /Проверк/i })).toBeVisible();
  });
});

