import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const approvalsMock = vi.hoisted(() => ({
  listRoutes: vi.fn(),
  createRoute: vi.fn(),
}));

vi.mock("@/api/approvals", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  approvalsApi: {
    listRoutes: (...args: unknown[]) => approvalsMock.listRoutes(...args),
    createRoute: (...args: unknown[]) => approvalsMock.createRoute(...args),
  },
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import ApprovalRoutesPage from "@/pages/approvals/ApprovalRoutesPage";

const routes = [
  {
    id: "r-1",
    code: "OT_DOCS",
    name: "Документы по охране труда",
    description: "Специалист → руководитель",
    applies_to: "document",
    status: "active",
  },
  {
    id: "r-2",
    code: "PACKS",
    name: "Комплекты клиенту",
    description: null,
    applies_to: "pack",
    status: "active",
  },
];

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <ApprovalRoutesPage />
      </MemoryRouter>,
    );
  });
};

describe("ApprovalRoutesPage", () => {
  beforeEach(() => {
    approvalsMock.listRoutes.mockReset();
    approvalsMock.createRoute.mockReset();
    approvalsMock.listRoutes.mockResolvedValue(routes);
  });

  it("показывает заведённые маршруты", async () => {
    await renderPage();

    expect(
      await screen.findByText(/Документы по охране труда/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Комплекты клиенту/)).toBeInTheDocument();
  });

  it("пустой список — это «маршрутов ещё нет», а не пустая страница", async () => {
    approvalsMock.listRoutes.mockResolvedValue([]);
    await renderPage();

    expect(await screen.findByText("Маршрутов ещё нет")).toBeInTheDocument();
  });

  it("экран в UX-бюджете на наполненных данных", async () => {
    await renderPage();
    await screen.findByText(/Документы по охране труда/);

    const budget = uxBudgetDelta(document.body, "ApprovalRoutesPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
