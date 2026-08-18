import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import PermitsPage from "@/pages/permits/PermitsPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import { useAuthStore } from "@/stores/auth";

const listPermitsMock = vi.fn();
const countPermitsMock = vi.fn();
const fetchAllPersonsMock = vi.fn();

vi.mock("@/api/permits", () => ({
  permitsApi: {
    listPermits: (...args: unknown[]) => listPermitsMock(...args),
    countPermits: (...args: unknown[]) => countPermitsMock(...args),
    createPermit: vi.fn(),
    updatePermit: vi.fn(),
    extendPermit: vi.fn(),
    revokePermit: vi.fn(),
  },
}));

vi.mock("@/api/personsApi", () => ({
  fetchAllPersons: (...args: unknown[]) => fetchAllPersonsMock(...args),
}));

const setUser = (permissions: string[]) =>
  useAuthStore.setState({
    user: {
      id: "u1",
      created_at: "2024-01-01",
      updated_at: "2024-01-01",
      email: "a@a.io",
      full_name: "Test User",
      roles: ["worker"],
      permissions,
    },
    loading: false,
    error: null,
    isAuthenticated: true,
    initialized: true,
  } as never);

describe("PermitsPage", () => {
  beforeEach(() => {
    listPermitsMock.mockReset();
    countPermitsMock.mockReset();
    fetchAllPersonsMock.mockReset();
    countPermitsMock.mockResolvedValue(0);
    fetchAllPersonsMock.mockResolvedValue([
      { id: "p1", full_name: "Иванов И. И." },
    ]);
  });

  it("shows empty state when there are no permits", async () => {
    listPermitsMock.mockResolvedValue({ items: [], total: 0 });
    setUser([PERMISSIONS.PERMIT_VIEW, PERMISSIONS.PERMIT_MANAGE]);
    render(
      <MemoryRouter>
        <PermitsPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/Допуски не найдены/i)).toBeInTheDocument();
  });

  it("renders a permit row with employee name and an expired badge", async () => {
    listPermitsMock.mockResolvedValue({
      items: [
        {
          id: "perm1",
          person_id: "p1",
          permit_type: "Работа на высоте",
          issued_at: "2025-01-01",
          valid_until: "2025-12-01",
          status: "active",
          is_expired: true,
          created_at: "2025-01-01T00:00:00Z",
          updated_at: "2025-01-01T00:00:00Z",
        },
      ],
      total: 1,
    });
    setUser([PERMISSIONS.PERMIT_VIEW, PERMISSIONS.PERMIT_MANAGE]);
    render(
      <MemoryRouter>
        <PermitsPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Иванов И. И.")).toBeInTheDocument();
    expect(screen.getByText("Просрочен")).toBeInTheDocument();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    listPermitsMock.mockResolvedValue({
      items: [
        {
          id: "perm1",
          person_id: "p1",
          permit_type: "Работа на высоте",
          issued_at: "2025-01-01",
          valid_until: "2025-12-01",
          status: "active",
          is_expired: true,
          created_at: "2025-01-01T00:00:00Z",
          updated_at: "2025-01-01T00:00:00Z",
        },
      ],
      total: 1,
    });
    setUser([PERMISSIONS.PERMIT_VIEW, PERMISSIONS.PERMIT_MANAGE]);
    render(
      <MemoryRouter>
        <PermitsPage />
      </MemoryRouter>,
    );
    await screen.findByText("Работа на высоте");

    const budget = uxBudgetDelta(document.body, "PermitsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("disables the create button without permit.manage permission", async () => {
    listPermitsMock.mockResolvedValue({ items: [], total: 0 });
    setUser([PERMISSIONS.PERMIT_VIEW]);
    render(
      <MemoryRouter>
        <PermitsPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("button", { name: /Новый допуск/i }),
    ).toBeDisabled();
  });
});
