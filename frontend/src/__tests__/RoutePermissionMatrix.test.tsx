import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { AccessDeniedPage } from "@/pages/access/AccessDeniedPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { ProtectedRoute } from "@/router/ProtectedRoute";
import { useAuthStore } from "@/stores/auth";

const ClientPortalPage = () => <div>Кабинет клиента</div>;
const AdminPage = () => <div>Админ-панель</div>;

describe("RoutePermissionMatrix", () => {
  beforeEach(() => {
    useAuthStore.setState({
      initialized: true,
      isAuthenticated: true,
      loading: false,
      error: null,
      user: {
        id: "u-1",
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
        email: "u@example.com",
        full_name: "User",
        roles: ["worker"],
        permissions: [PERMISSIONS.DASHBOARD_VIEW]
      }
    });
  });

  it("isolates client portal route for unauthorized role", () => {
    render(
      <MemoryRouter initialEntries={["/client-portal/dashboard"]}>
        <Routes>
          <Route element={<ProtectedRoute permission={PERMISSIONS.CLIENT_PORTAL_VIEW} />}>
            <Route path="/client-portal/dashboard" element={<ClientPortalPage />} />
          </Route>
          <Route path="/no-access" element={<AccessDeniedPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("Доступ ограничен")).toBeInTheDocument();
    expect(screen.queryByText("Кабинет клиента")).not.toBeInTheDocument();
  });

  it("allows admin route only for admin permission", () => {
    useAuthStore.setState((state) => ({
      ...state,
      user: state.user
        ? { ...state.user, permissions: [PERMISSIONS.ADMIN_MANAGE_ROLES] }
        : null
    }));

    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route element={<ProtectedRoute permission={PERMISSIONS.ADMIN_MANAGE_ROLES} />}>
            <Route path="/admin" element={<AdminPage />} />
          </Route>
          <Route path="/no-access" element={<AccessDeniedPage />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText("Админ-панель")).toBeInTheDocument();
  });
});
