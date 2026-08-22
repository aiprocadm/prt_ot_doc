import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import LoginPage from "@/pages/auth/LoginPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

vi.mock("@/api/tenantStorage", () => ({
  tenantStorage: {
    getTenant: () => null,
    // `api/client.ts` зовёт hydrate() при ИМПОРТЕ модуля: страница входа
    // теперь дотягивается до него через хранилище бренда (BIZ-52 срез-6),
    // и заглушка без hydrate роняла бы сбор теста, а не проверку.
    hydrate: () => undefined,
  },
}));

// BIZ-52 срез-5: на экране входа появились ссылки на юр. тексты. Тест про
// форму, а не про сеть — подменяем список, иначе он тянет настоящий API-клиент.
vi.mock("@/api/legalDocuments", () => ({
  listLegalDocuments: async () => [],
}));

const mockAuthState = {
  login: vi.fn(),
  loading: false,
  isAuthenticated: false,
};

vi.mock("@/stores/auth", () => ({
  useAuthStore: (selector?: (state: typeof mockAuthState) => unknown) =>
    typeof selector === "function" ? selector(mockAuthState) : mockAuthState,
}));

describe("LoginPage smoke", () => {
  it("renders login form controls", () => {
    render(
      <MemoryRouter initialEntries={["/auth/login"]}>
        <Routes>
          <Route path="/auth/login" element={<LoginPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Вход в платформу" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Тенант")).toBeInTheDocument();
    expect(screen.getByLabelText("E-mail")).toBeInTheDocument();
    expect(screen.getByLabelText("Пароль")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
  });

  it("экран в UX-бюджете (BIZ-60 волна 5)", async () => {
    // act(async …): LegalLinks грузит юр. тексты эффектом — даём промису
    // завершиться, чтобы мерить устоявшийся экран, а не полукадр отрисовки.
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/auth/login"]}>
          <Routes>
            <Route path="/auth/login" element={<LoginPage />} />
          </Routes>
        </MemoryRouter>,
      );
    });

    const budget = uxBudgetDelta(document.body, "LoginPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
