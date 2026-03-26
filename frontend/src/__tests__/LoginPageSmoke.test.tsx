import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import LoginPage from "@/pages/auth/LoginPage";

vi.mock("@/api/tenantStorage", () => ({
  tenantStorage: {
    getTenant: () => null
  }
}));

const mockAuthState = {
  login: vi.fn(),
  loading: false,
  isAuthenticated: false
};

vi.mock("@/stores/auth", () => ({
  useAuthStore: (selector?: (state: typeof mockAuthState) => unknown) =>
    typeof selector === "function" ? selector(mockAuthState) : mockAuthState
}));

describe("LoginPage smoke", () => {
  it("renders login form controls", () => {
    render(
      <MemoryRouter initialEntries={["/auth/login"]}>
        <Routes>
          <Route path="/auth/login" element={<LoginPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByRole("heading", { name: "Вход в платформу" })).toBeInTheDocument();
    expect(screen.getByLabelText("Tenant")).toBeInTheDocument();
    expect(screen.getByLabelText("E-mail")).toBeInTheDocument();
    expect(screen.getByLabelText("Пароль")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
  });
});
