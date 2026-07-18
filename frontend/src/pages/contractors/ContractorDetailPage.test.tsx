import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import ContractorDetailPage from "./ContractorDetailPage";
import { contractorsApi } from "@/api/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      getRegistry: vi.fn(),
      getComplianceSummary: vi.fn(),
      listEmployees: vi.fn(),
      listIncidents: vi.fn(),
      listDocuments: vi.fn()
    }
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function" ? (children as (v: boolean) => unknown)(true) : children
}));

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.getRegistry as any).mockResolvedValue({ id: "c1", name: "ООО Подрядчик", status: "active", inn: "7701" });
  (contractorsApi.getComplianceSummary as any).mockResolvedValue({
    employees_total: 3,
    admission: { valid: 2, pending: 1 },
    training: { valid: 3 },
    medical: { pending: 3 }
  });
  (contractorsApi.listEmployees as any).mockResolvedValue({ items: [], total: 0 });
  (contractorsApi.listIncidents as any).mockResolvedValue({ items: [], total: 0 });
  (contractorsApi.listDocuments as any).mockResolvedValue({ items: [], total: 0 });
});

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/contractors/c1"]}>
      <Routes>
        <Route path="/contractors/:id" element={<ContractorDetailPage />} />
      </Routes>
    </MemoryRouter>
  );

describe("ContractorDetailPage", () => {
  it("renders the header and compliance KPI", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: /ООО Подрядчик/ })).toBeInTheDocument();
    expect(await screen.findByText("Сотрудников: 3")).toBeInTheDocument();
  });

  it("shows all four tabs", async () => {
    renderPage();
    expect(await screen.findByRole("tab", { name: "Обзор" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Сотрудники" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Документы" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Инциденты" })).toBeInTheDocument();
  });
});
