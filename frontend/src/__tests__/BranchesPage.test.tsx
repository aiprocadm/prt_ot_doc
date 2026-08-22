import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => apiClientMock.get(...args),
    post: (...args: unknown[]) => apiClientMock.post(...args),
    patch: (...args: unknown[]) => apiClientMock.patch(...args),
    delete: (...args: unknown[]) => apiClientMock.delete(...args),
  },
}));

import BranchesPage from "@/pages/branches/BranchesPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";
import { useBranchesStore } from "@/stores/branches";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const branchManager = {
  id: "branch-manager",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  email: "branch.manager@example.com",
  full_name: "Branch Manager",
  roles: [],
  permissions: [PERMISSIONS.BRANCH_MANAGE],
  attributes: { tenant_id: "tenant-1" },
};

const companiesResponse = [
  { id: "company-1", name: "АО Ромашка", inn: "7701234567" },
  { id: "company-2", name: "ООО Василёк", inn: "7707654321" },
];

const branchesResponse = [
  {
    id: "branch-1",
    company_id: "company-1",
    name: "Центральный филиал",
    code: "MSK-01",
    contact_name: "Иванов Иван",
    contact_phone: "+7 495 111-22-33",
    status: "active",
  },
  {
    id: "branch-2",
    company_id: "company-2",
    name: "Северный филиал",
    status: "inactive",
  },
];

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <BranchesPage />
      </MemoryRouter>,
    );
  });
};

describe("BranchesPage", () => {
  beforeEach(() => {
    apiClientMock.get.mockReset();
    apiClientMock.post.mockReset();
    apiClientMock.patch.mockReset();
    apiClientMock.delete.mockReset();
    useBranchesStore.getState().reset();
    useAuthStore.setState({
      user: branchManager,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });

    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/companies") {
        return Promise.resolve({ data: { items: companiesResponse } });
      }
      if (url === "/branches") {
        return Promise.resolve({
          data: { items: branchesResponse, total: branchesResponse.length },
        });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
  });

  it("renders filled branches list with companies filter", async () => {
    await renderPage();

    expect(await screen.findByText("Центральный филиал")).toBeInTheDocument();
    expect(await screen.findByText("Северный филиал")).toBeInTheDocument();
    // Компания видна и в фильтре (option), и в колонке таблицы.
    expect(screen.getAllByText("АО Ромашка").length).toBeGreaterThan(1);
    expect(
      screen.getByRole("button", { name: "Новый филиал" }),
    ).toBeEnabled();
  });

  it("экран в UX-бюджете на наполненных данных (BIZ-60)", async () => {
    // Меряем НАПОЛНЕННЫЙ экран: непустой список филиалов и загруженный фильтр
    // компаний — пустое состояние занизило бы и колонки, и кнопки строк.
    await renderPage();
    expect(await screen.findByText("Центральный филиал")).toBeInTheDocument();
    expect(await screen.findByText("Северный филиал")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "BranchesPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
