import { expect, test } from "@playwright/test";

const canRun =
  process.env.E2E_RUN_KEY_SCENARIOS === "1" &&
  Boolean(process.env.E2E_USER_EMAIL) &&
  Boolean(process.env.E2E_USER_PASSWORD);

test.describe("key user scenarios", () => {
  test.skip(!canRun, "Set E2E_RUN_KEY_SCENARIOS=1, E2E_USER_EMAIL and E2E_USER_PASSWORD");

  test("create company flow opens from companies page", async ({ page }) => {
    const tenant = process.env.E2E_TENANT ?? "demo";
    await page.goto("/auth/login");
    await page.getByLabel("Tenant").fill(tenant);
    await page.getByLabel("E-mail").fill(process.env.E2E_USER_EMAIL!);
    await page.getByLabel("Пароль").fill(process.env.E2E_USER_PASSWORD!);
    await page.getByRole("button", { name: "Войти" }).click();

    await page.goto("/companies");
    await expect(page.getByRole("heading", { name: /Компани/i })).toBeVisible();
  });

  test("upload document flow opens document wizard", async ({ page }) => {
    const tenant = process.env.E2E_TENANT ?? "demo";
    await page.goto("/auth/login");
    await page.getByLabel("Tenant").fill(tenant);
    await page.getByLabel("E-mail").fill(process.env.E2E_USER_EMAIL!);
    await page.getByLabel("Пароль").fill(process.env.E2E_USER_PASSWORD!);
    await page.getByRole("button", { name: "Войти" }).click();

    await page.goto("/documents/wizard");
    await expect(page).toHaveURL(/\/documents\/wizard/);
  });

  test("assign task flow opens task registry", async ({ page }) => {
    const tenant = process.env.E2E_TENANT ?? "demo";
    await page.goto("/auth/login");
    await page.getByLabel("Tenant").fill(tenant);
    await page.getByLabel("E-mail").fill(process.env.E2E_USER_EMAIL!);
    await page.getByLabel("Пароль").fill(process.env.E2E_USER_PASSWORD!);
    await page.getByRole("button", { name: "Войти" }).click();

    await page.goto("/tasks");
    await expect(page.getByRole("heading", { name: /Задач/i })).toBeVisible();
  });

  test("run inspection flow opens inspections page", async ({ page }) => {
    const tenant = process.env.E2E_TENANT ?? "demo";
    await page.goto("/auth/login");
    await page.getByLabel("Tenant").fill(tenant);
    await page.getByLabel("E-mail").fill(process.env.E2E_USER_EMAIL!);
    await page.getByLabel("Пароль").fill(process.env.E2E_USER_PASSWORD!);
    await page.getByRole("button", { name: "Войти" }).click();

    await page.goto("/inspections");
    await expect(page.getByRole("heading", { name: /Проверк/i })).toBeVisible();
  });
});

