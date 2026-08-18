import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { listMock, createMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  createMock: vi.fn(),
}));

const mockInspection = {
  id: "insp-1",
  inspection_type: "planned",
  authority: "Роструд",
  status: "planned",
  company_id: "c-1",
  site_id: null,
  purpose: "Плановая проверка условий труда",
  scheduled_at: "2024-07-15T09:00:00Z",
  created_at: "2024-06-01T11:00:00Z",
  updated_at: "2024-06-01T11:00:00Z",
};

vi.mock("@/api/inspections", () => ({
  inspectionsApi: {
    list: listMock,
    create: createMock,
    listResults: vi.fn().mockResolvedValue([]),
  },
}));

import { PERMISSIONS } from "@/permissions/permissions";
import InspectionsPage from "@/pages/inspections/InspectionsPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import { useAuthStore } from "@/stores/auth";

const userWithInspectionCreate = {
  id: "user-inspection-create",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  email: "inspection.lead@example.com",
  full_name: "Inspection Lead",
  roles: ["worker"],
  permissions: [PERMISSIONS.INSPECTION_VIEW, PERMISSIONS.INSPECTION_CREATE],
  attributes: { tenant_id: "tenant-1" },
};

const userWithoutInspectionCreate = {
  ...userWithInspectionCreate,
  id: "user-inspection-view",
  email: "inspection.viewer@example.com",
  permissions: [PERMISSIONS.INSPECTION_VIEW],
};

describe("InspectionsPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    createMock.mockReset();
    useAuthStore.setState({
      user: userWithInspectionCreate,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });
  });

  it("renders inspections list after loading", async () => {
    listMock.mockResolvedValue({ items: [mockInspection], total: 1 });

    render(
      <MemoryRouter>
        <InspectionsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Роструд")).toBeInTheDocument();
    });
    expect(screen.getByText("Плановая")).toBeInTheDocument();
    expect(screen.getAllByText("Запланирована").length).toBeGreaterThan(0);
    expect(listMock).toHaveBeenCalledOnce();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    listMock.mockResolvedValue({ items: [mockInspection], total: 1 });

    render(
      <MemoryRouter>
        <InspectionsPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Роструд")).toBeInTheDocument();
    });

    const budget = uxBudgetDelta(document.body, "InspectionsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("shows empty state when no inspections", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });

    render(
      <MemoryRouter>
        <InspectionsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/проверки не найдены/i)).toBeInTheDocument();
    });
  });

  it("opens create dialog when button clicked", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <InspectionsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /создать проверку/i }),
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /создать проверку/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/орган/i)).toBeInTheDocument();
  });

  it("shows disabled create action without create permission", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });
    useAuthStore.setState({
      user: userWithoutInspectionCreate,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });

    render(
      <MemoryRouter>
        <InspectionsPage />
      </MemoryRouter>,
    );

    const button = await screen.findByRole("button", {
      name: /создать проверку/i,
    });
    expect(button).toBeDisabled();
  });
});
