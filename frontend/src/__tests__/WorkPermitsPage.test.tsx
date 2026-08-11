import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import WorkPermitsPage from "@/pages/work-permits/WorkPermitsPage";
import { useAuthStore } from "@/stores/auth";

const listMock = vi.fn();
const countMock = vi.fn();

vi.mock("@/api/workPermits", () => ({
  workPermitsApi: {
    list: (...a: unknown[]) => listMock(...a),
    count: (...a: unknown[]) => countMock(...a),
  },
}));

// Use a non-admin role so isAdminUser() returns false and permission gating is enforced
const setRole = (perms: string[]) =>
  useAuthStore.setState({
    user: { id: "u1", roles: ["ot_specialist"], permissions: perms } as never,
    loading: false,
    error: null,
    isAuthenticated: true,
    initialized: true,
  });

describe("WorkPermitsPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    countMock.mockReset();
    listMock.mockResolvedValue({ items: [], total: 0 });
    countMock.mockResolvedValue(0);
  });

  it("показывает заголовок страницы", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW, PERMISSIONS.WORK_PERMIT_MANAGE]);
    render(
      <MemoryRouter>
        <WorkPermitsPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", { name: /наряды-допуски/i }),
    ).toBeInTheDocument();
  });

  it("скрывает «Новый наряд» без права manage", async () => {
    setRole([PERMISSIONS.WORK_PERMIT_VIEW]);
    render(
      <MemoryRouter>
        <WorkPermitsPage />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: /наряды-допуски/i });
    expect(
      screen.queryByRole("button", { name: /новый наряд/i }),
    ).not.toBeInTheDocument();
  });
});
