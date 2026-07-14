import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import ContractorsPage from "./ContractorsPage";
import { contractorsApi } from "@/api/contractors";

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
      deleteRequirement: vi.fn()
    }
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function" ? (children as (v: boolean) => unknown)(true) : children
}));

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.listRegistry as any).mockResolvedValue({
    items: [{ id: "c1", name: "ООО Подрядчик", status: "active", company_id: null }],
    total: 1
  });
  (contractorsApi.listEmployees as any).mockResolvedValue({ items: [{ id: "e1", contractor_id: "c1" }], total: 1 });
  (contractorsApi.listIncidents as any).mockResolvedValue({ items: [], total: 0 });
  (contractorsApi.listExpiringDocuments as any).mockResolvedValue({ items: [], total: 0 });
  (contractorsApi.listRequirements as any).mockResolvedValue({ items: [], total: 0 });
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <ContractorsPage />
    </MemoryRouter>
  );

describe("ContractorsPage registry tab", () => {
  it("renders the registry from contractorsApi", async () => {
    renderPage();
    expect(await screen.findByText("ООО Подрядчик")).toBeInTheDocument();
  });

  it("creates a contractor via the dialog", async () => {
    (contractorsApi.createRegistry as any).mockResolvedValue({ id: "c2", name: "Новый", status: "active" });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Новый контрагент" }));
    fireEvent.change(await screen.findByLabelText("Название"), { target: { value: "Новый" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(contractorsApi.createRegistry).toHaveBeenCalledWith(expect.objectContaining({ name: "Новый" }))
    );
  });

  it("still renders the registry when expiring-docs is feature-disabled (404)", async () => {
    (contractorsApi.listExpiringDocuments as any).mockRejectedValue({
      status: 404,
      message: "Contractors feature is not enabled for this tenant"
    });
    renderPage();
    // The ungated registry must survive a feature-disabled expiring-docs call
    // (not collapse the whole page into an error state).
    expect(await screen.findByText("ООО Подрядчик")).toBeInTheDocument();
  });
});
