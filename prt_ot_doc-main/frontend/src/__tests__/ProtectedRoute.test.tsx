import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { ProtectedRoute } from "@/router/ProtectedRoute";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";
import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";

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
          <Route element={<ProtectedRoute permission={PERMISSIONS.DOCUMENT_VIEW} />}>
            <Route path="/secure" element={<PrivatePage />} />
          </Route>
          <Route path="/auth/login" element={<LoginPage />} />
          <Route path="/no-access" element={<AccessDeniedPage />} />
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
    useAuthStore.setState({
      initialized: true,
      isAuthenticated: true,
      user: {
        id: "user-3",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "user@example.com",
        full_name: "User",
        roles: ["ot_specialist"],
        permissions: [PERMISSIONS.DOCUMENT_VIEW]
      }
    });
    renderWithRouter();
    expect(screen.getByText("Приватный контент")).toBeInTheDocument();
  });

  it("показывает сообщение при отсутствии прав", () => {
    useAuthStore.setState({
      initialized: true,
      isAuthenticated: true,
      user: {
        id: "user-4",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "user@example.com",
        full_name: "User",
        roles: ["worker"],
        permissions: [PERMISSIONS.DASHBOARD_VIEW]
      }
    });
    renderWithRouter();
    expect(screen.getByText("Доступ ограничен")).toBeInTheDocument();
  });
});
