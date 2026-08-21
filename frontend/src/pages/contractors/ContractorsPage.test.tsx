import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import ContractorsPage from "./ContractorsPage";
import { contractorsApi } from "@/api/contractors";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      listRegistry: vi.fn(),
      listEmployees: vi.fn(),
      listIncidents: vi.fn(),
      listExpiringDocuments: vi.fn(),
      listRequirements: vi.fn(),
      createRegistry: vi.fn(),
      createRequirement: vi.fn(),
      deleteRequirement: vi.fn(),
    },
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function"
      ? (children as (v: boolean) => unknown)(true)
      : children,
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(contractorsApi.listRegistry).mockResolvedValue({
    items: [
      { id: "c1", name: "ООО Подрядчик", status: "active", company_id: null },
    ],
    total: 1,
  });
  vi.mocked(contractorsApi.listEmployees).mockResolvedValue({
    items: [
      {
        id: "e1",
        contractor_id: "c1",
        full_name: "Сидоров С.С.",
        access_status: "pending",
        training_status: "valid",
        medical_status: "valid",
      },
    ],
    total: 1,
  });
  vi.mocked(contractorsApi.listIncidents).mockResolvedValue({
    items: [],
    total: 0,
  });
  vi.mocked(contractorsApi.listExpiringDocuments).mockResolvedValue({
    items: [],
    total: 0,
  });
  vi.mocked(contractorsApi.listRequirements).mockResolvedValue({
    items: [],
    total: 0,
  });
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <ContractorsPage />
    </MemoryRouter>,
  );

describe("ContractorsPage registry tab", () => {
  it("renders the registry from contractorsApi", async () => {
    renderPage();
    expect(await screen.findByText("ООО Подрядчик")).toBeInTheDocument();
  });

  it("creates a contractor via the dialog", async () => {
    vi.mocked(contractorsApi.createRegistry).mockResolvedValue({
      id: "c2",
      name: "Новый",
      status: "active",
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Новый контрагент" }),
    );
    fireEvent.change(await screen.findByLabelText("Название"), {
      target: { value: "Новый" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(contractorsApi.createRegistry).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Новый" }),
      ),
    );
  });

  it("still renders the registry when expiring-docs is feature-disabled (404)", async () => {
    vi.mocked(contractorsApi.listExpiringDocuments).mockRejectedValue({
      status: 404,
      message: "Contractors feature is not enabled for this tenant",
    });
    renderPage();
    // The ungated registry must survive a feature-disabled expiring-docs call
    // (not collapse the whole page into an error state).
    expect(await screen.findByText("ООО Подрядчик")).toBeInTheDocument();
  });
  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    renderPage();
    // Наполненное состояние: строка реестра из фикстуры видна в таблице.
    // Мерить пустой/загрузочный экран — самообман (урок NotificationsPage).
    expect(await screen.findByText("ООО Подрядчик")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "ContractorsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
