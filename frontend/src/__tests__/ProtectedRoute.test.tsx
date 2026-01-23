import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { ProtectedRoute } from "@/router/ProtectedRoute";
import { useAuthStore } from "@/stores/auth";

const PrivatePage = () => <div>Приватный контент</div>;
const LoginPage = () => <div>Страница входа</div>;

describe("ProtectedRoute", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      loading: false,
      error: null,
      isAuthenticated: false,
      initialized: false
    });
  });

  const renderWithRouter = () =>
    render(
      <MemoryRouter initialEntries={["/secure"]}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/secure" element={<PrivatePage />} />
          </Route>
          <Route path="/auth/login" element={<LoginPage />} />
        </Routes>
      </MemoryRouter>
    );

  it("показывает индикатор загрузки до инициализации", () => {
    renderWithRouter();
    expect(screen.getByRole("status")).toHaveTextContent("Проверка сессии");
  });

  it("перенаправляет на логин, если пользователь не аутентифицирован", () => {
    useAuthStore.setState({ initialized: true, isAuthenticated: false });
    renderWithRouter();
    expect(screen.getByText("Страница входа")).toBeInTheDocument();
  });

  it("отображает приватный контент для аутентифицированного пользователя", () => {
    useAuthStore.setState({ initialized: true, isAuthenticated: true });
    renderWithRouter();
    expect(screen.getByText("Приватный контент")).toBeInTheDocument();
  });
});
