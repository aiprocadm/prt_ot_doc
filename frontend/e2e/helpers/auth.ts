import { expect, type Page } from "@playwright/test";

const resolveTenant = () => process.env.E2E_TENANT ?? "demo";

export const loginWithCredentials = async (page: Page, email: string, password: string) => {
  await page.goto("/auth/login", { waitUntil: "domcontentloaded" });
  await page.getByLabel("Тенант").fill(resolveTenant());
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Пароль").fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page).not.toHaveURL(/\/auth\/login/, { timeout: 45_000 });
};

export const loginDefaultUser = async (page: Page) => {
  const email = process.env.E2E_USER_EMAIL;
  const password = process.env.E2E_USER_PASSWORD;
  if (!email || !password) {
    throw new Error("E2E_USER_EMAIL and E2E_USER_PASSWORD are required");
  }
  await loginWithCredentials(page, email, password);
};

export const loginLimitedUser = async (page: Page) => {
  const email = process.env.E2E_LIMITED_USER_EMAIL;
  const password = process.env.E2E_LIMITED_USER_PASSWORD;
  if (!email || !password) {
    throw new Error("E2E_LIMITED_USER_EMAIL and E2E_LIMITED_USER_PASSWORD are required");
  }
  await loginWithCredentials(page, email, password);
};
