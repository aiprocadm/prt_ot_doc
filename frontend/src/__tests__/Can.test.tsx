import { render, screen } from "@testing-library/react";
import { describe, it, beforeEach, expect } from "vitest";

import { Can } from "@/components/permissions/Can";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";

const userWithPermissions = {
  id: "user-2",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  email: "viewer@example.com",
  full_name: "Viewer",
  roles: ["worker"],
  permissions: [PERMISSIONS.DOCUMENT_VIEW],
  attributes: { tenant_id: "tenant-1" },
};

describe("Can", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: userWithPermissions,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });
  });

  it("рендерит детей при наличии прав", () => {
    render(
      <Can permission={PERMISSIONS.DOCUMENT_VIEW}>
        <div>Есть доступ</div>
      </Can>,
    );
    expect(screen.getByText("Есть доступ")).toBeInTheDocument();
  });

  it("рендерит fallback при отсутствии прав", () => {
    render(
      <Can
        permission={PERMISSIONS.ADMIN_MANAGE_ROLES}
        fallback={<div>Нет доступа</div>}
      >
        <div>Скрыто</div>
      </Can>,
    );
    expect(screen.getByText("Нет доступа")).toBeInTheDocument();
  });

  it("поддерживает render-prop", () => {
    render(
      <Can permission={PERMISSIONS.ADMIN_MANAGE_ROLES}>
        {(allowed) => <span>{String(allowed)}</span>}
      </Can>,
    );
    expect(screen.getByText("false")).toBeInTheDocument();
  });
});
