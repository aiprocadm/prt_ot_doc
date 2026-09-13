import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import PpePage from "@/pages/ppe/PpePage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import { useAuthStore } from "@/stores/auth";

const getPpeOverviewMock = vi.fn();

vi.mock("@/api/ops", () => ({
  opsApi: {
    getPpeOverview: (...args: unknown[]) => getPpeOverviewMock(...args),
  },
}));

const baseUser = {
  id: "user-ppe",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  email: "ppe@example.com",
  full_name: "PPE User",
  roles: ["worker"],
  permissions: [PERMISSIONS.PPE_VIEW],
  attributes: { tenant_id: "tenant-1" },
};

describe("PpePage", () => {
  beforeEach(() => {
    getPpeOverviewMock.mockReset();
    getPpeOverviewMock.mockResolvedValue({
      items: [
        { id: "item-1", name: "Каска", code: "helmet", category: "head" },
      ],
      issues: [
        {
          id: "issue-1",
          person_id: "person-1",
          item_id: "item-1",
          quantity: 1,
          status: "issued",
          expires_at: "2020-01-01T00:00:00Z",
        },
      ],
      persons: [
        {
          id: "person-1",
          created_at: "2024-01-01",
          updated_at: "2024-01-02",
          first_name: "Иван",
          last_name: "Иванов",
          middle_name: null,
          full_name: "Иван Иванов",
          position: "Сварщик",
          company_id: "company-1",
          status: "active",
        },
      ],
    });
  });

  it("называет разделы, закрытые правами, и не гасит экран (срез-167)", async () => {
    getPpeOverviewMock.mockResolvedValue({
      items: [
        { id: "item-1", name: "Каска", code: "helmet", category: "head" },
      ],
      issues: [],
      expiring: [],
      persons: [],
      denied: ["сотрудники"],
    });
    useAuthStore.setState({
      user: baseUser,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });

    render(
      <MemoryRouter>
        <PpePage />
      </MemoryRouter>,
    );

    // Про закрытую часть сказано словами, а не пустотой.
    const notice = await screen.findByText(
      /у вашей роли нет доступа к разделам/i,
    );
    expect(notice).toBeInTheDocument();
    expect(notice.textContent).toContain("сотрудники");
    // Экран при этом жив: общая ошибка загрузки не показана.
    expect(screen.queryByText(/Не удалось загрузить/i)).toBeNull();
  });

  it("показывает disabled quick issue action без write permission", async () => {
    useAuthStore.setState({
      user: baseUser,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });

    render(
      <MemoryRouter>
        <PpePage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("button", { name: /быстрая выдача/i }),
    ).toBeDisabled();
  });

  it("показывает enabled quick issue action при наличии write permission", async () => {
    useAuthStore.setState({
      user: {
        ...baseUser,
        permissions: [PERMISSIONS.PPE_VIEW, PERMISSIONS.PPE_ISSUE],
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });

    render(
      <MemoryRouter>
        <PpePage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("button", { name: /быстрая выдача/i }),
    ).toBeEnabled();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    useAuthStore.setState({
      user: {
        ...baseUser,
        permissions: [PERMISSIONS.PPE_VIEW, PERMISSIONS.PPE_ISSUE],
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });
    render(
      <MemoryRouter>
        <PpePage />
      </MemoryRouter>,
    );
    await screen.findByRole("button", { name: /быстрая выдача/i });

    const budget = uxBudgetDelta(document.body, "PpePage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("applies status filter from query params", async () => {
    useAuthStore.setState({
      user: {
        ...baseUser,
        permissions: [PERMISSIONS.PPE_VIEW, PERMISSIONS.PPE_ISSUE],
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });

    render(
      <MemoryRouter initialEntries={["/ppe?status=overdue"]}>
        <PpePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Требует замены")).toBeInTheDocument();
  });

  it("shows a link to mobile issuance for users who can issue", async () => {
    useAuthStore.setState({
      user: {
        ...baseUser,
        permissions: [PERMISSIONS.PPE_VIEW, PERMISSIONS.PPE_ISSUE],
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });

    render(
      <MemoryRouter>
        <PpePage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("button", { name: /мобильная выдача/i }),
    ).toBeEnabled();
  });
});
