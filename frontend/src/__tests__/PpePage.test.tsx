import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import PpePage from "@/pages/ppe/PpePage";
import { useAuthStore } from "@/stores/auth";

const getPpeOverviewMock = vi.fn();

vi.mock("@/api/ops", () => ({
  opsApi: {
    getPpeOverview: (...args: unknown[]) => getPpeOverviewMock(...args)
  }
}));

const baseUser = {
  id: "user-ppe",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  email: "ppe@example.com",
  full_name: "PPE User",
  roles: ["worker"],
  permissions: [PERMISSIONS.PPE_VIEW],
  attributes: { tenant_id: "tenant-1" }
};

describe("PpePage", () => {
  beforeEach(() => {
    getPpeOverviewMock.mockReset();
    getPpeOverviewMock.mockResolvedValue({ issues: [], items: [], persons: [] });
  });

  it("показывает disabled quick issue action без write permission", async () => {
    useAuthStore.setState({
      user: baseUser,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });

    render(
      <MemoryRouter>
        <PpePage />
      </MemoryRouter>
    );

    expect(await screen.findByRole("button", { name: /быстрая выдача/i })).toBeDisabled();
  });

  it("показывает enabled quick issue action при наличии write permission", async () => {
    useAuthStore.setState({
      user: { ...baseUser, permissions: [PERMISSIONS.PPE_VIEW, PERMISSIONS.PPE_ISSUE] },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });

    render(
      <MemoryRouter>
        <PpePage />
      </MemoryRouter>
    );

    expect(await screen.findByRole("button", { name: /быстрая выдача/i })).toBeEnabled();
  });
});