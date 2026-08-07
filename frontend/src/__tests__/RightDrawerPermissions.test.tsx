import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, beforeEach, expect } from "vitest";

import { RightDrawer } from "@/components/layout/RightDrawer";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";

const baseUser = {
  id: "user-5",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  email: "user@example.com",
  full_name: "User",
  roles: ["worker"],
  permissions: [PERMISSIONS.DASHBOARD_VIEW],
};

describe("RightDrawer permission visibility", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: baseUser,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });
  });

  it("скрывает создание документа без прав", () => {
    render(
      <MemoryRouter>
        <RightDrawer />
      </MemoryRouter>,
    );
    expect(screen.queryByText("Создать документ")).not.toBeInTheDocument();
  });

  it("показывает создание документа при наличии прав", () => {
    useAuthStore.setState({
      user: { ...baseUser, permissions: [PERMISSIONS.DOCUMENT_CREATE] },
      isAuthenticated: true,
      initialized: true,
    });
    render(
      <MemoryRouter>
        <RightDrawer />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("link", { name: /создать документ/i }),
    ).toHaveAttribute("href", "/documents/wizard");
  });
});
