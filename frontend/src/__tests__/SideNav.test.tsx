import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NavMenuProvider } from "@/components/layout/NavMenuProvider";
import { SideNav } from "@/components/layout/SideNav";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";
import { renderWithRouter } from "@/test-utils/renderWithRouter";

const renderSideNav = () =>
  renderWithRouter(
    <NavMenuProvider>
      <SideNav />
    </NavMenuProvider>
  );

vi.mock("@/api/billing", () => ({
  getBillingSummary: vi.fn(
    () => new Promise(() => undefined)
  )
}));

describe("SideNav", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: "nav-user",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "nav@example.com",
        full_name: "Nav User",
        roles: ["worker"],
        permissions: [PERMISSIONS.DASHBOARD_VIEW, PERMISSIONS.DOCUMENT_VIEW],
        attributes: { tenant_id: "tenant-1" }
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });
  });

  it("hides generation link without document create permission", () => {
    renderSideNav();

    expect(screen.queryByRole("link", { name: "Генерация" })).not.toBeInTheDocument();
  });

  it("shows generation link with document create permission", () => {
    useAuthStore.setState((state) => ({
      ...state,
      user: state.user
        ? {
            ...state.user,
            permissions: [PERMISSIONS.DASHBOARD_VIEW, PERMISSIONS.DOCUMENT_VIEW, PERMISSIONS.DOCUMENT_CREATE]
          }
        : null
    }));

    renderSideNav();

    expect(screen.getByRole("link", { name: "Генерация" })).toHaveAttribute("href", "/generation");
  });
});
