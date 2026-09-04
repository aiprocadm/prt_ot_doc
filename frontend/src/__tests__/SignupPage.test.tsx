import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ signup: vi.fn() }));

vi.mock("@/api/signup", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  signup: api.signup,
}));

import SignupPage from "@/pages/auth/SignupPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

/**
 * Самостоятельная регистрация (BIZ-53 срез-3, разд. 53.2).
 *
 * Главное здесь — что ЗАКРЫТАЯ регистрация объясняется словами. Ручка выключена
 * по умолчанию и отвечает 404; общая ошибка на этом месте оставила бы человека
 * гадать, сломалось оно или так задумано.
 */

const fill = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByLabelText("Название организации"), "ООО Ромашка");
  await user.type(
    screen.getByLabelText("Адрес рабочего пространства"),
    "romashka",
  );
  await user.type(
    screen.getByLabelText("Электронная почта владельца"),
    "owner@romashka.ru",
  );
  await user.type(screen.getByLabelText("Пароль"), "Secret123!");
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <SignupPage />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SignupPage", () => {
  it("создаёт пространство и показывает, чем входить", async () => {
    api.signup.mockResolvedValue({
      tenant_slug: "romashka",
      owner_email: "owner@romashka.ru",
      plan_code: "free",
      warnings: [],
    });
    const user = userEvent.setup();
    renderPage();
    await fill(user);

    await user.click(screen.getByRole("button", { name: "Создать" }));

    const done = await screen.findByTestId("signup-done");
    expect(done).toHaveTextContent("romashka");
    expect(done).toHaveTextContent("owner@romashka.ru");
  });

  it("закрытая регистрация объяснена словами, а не ошибкой", async () => {
    api.signup.mockRejectedValue({ status: 404, message: "Not found" });
    const user = userEvent.setup();
    renderPage();
    await fill(user);

    await user.click(screen.getByRole("button", { name: "Создать" }));

    const closed = await screen.findByTestId("signup-closed");
    expect(closed).toHaveTextContent(/закрыта/);
    expect(closed).toHaveTextContent(/владельцу платформы/);
  });

  it("занятый адрес объяснён отдельно от прочих сбоев", async () => {
    api.signup.mockRejectedValue({
      status: 409,
      message: "Tenant already exists",
    });
    const user = userEvent.setup();
    renderPage();
    await fill(user);

    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByTestId("signup-error")).toHaveTextContent(
      /уже занят/,
    );
  });

  it("перебор объяснён отдельно от прочих сбоев", async () => {
    api.signup.mockRejectedValue({ status: 429, message: "Too many" });
    const user = userEvent.setup();
    renderPage();
    await fill(user);

    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByTestId("signup-error")).toHaveTextContent(
      /Слишком много попыток/,
    );
  });

  it("предупреждения выдачи показаны, а не спрятаны", async () => {
    // Иначе человек увидит пустые справочники и не поймёт, почему.
    api.signup.mockResolvedValue({
      tenant_slug: "romashka",
      owner_email: "owner@romashka.ru",
      plan_code: "free",
      warnings: ["starter_pack_missing:industry"],
    });
    const user = userEvent.setup();
    renderPage();
    await fill(user);

    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByTestId("signup-done")).toHaveTextContent(
      "starter_pack_missing:industry",
    );
  });

  it("экран в UX-бюджете (BIZ-60)", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Пароль")).toBeInTheDocument(),
    );

    const budget = uxBudgetDelta(document.body, "SignupPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
