import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { ContractorIncidentsTab } from "./ContractorIncidentsTab";
import { contractorsApi } from "@/api/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      listIncidents: vi.fn(),
      createIncident: vi.fn()
    }
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function" ? (children as (v: boolean) => unknown)(true) : children
}));

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.listIncidents as any).mockResolvedValue({
    items: [{ id: "i1", contractor_id: "c1", incident_type: "падение", severity: "high", status: "open", occurred_at: "2026-06-01T10:00:00Z" }],
    total: 1
  });
  (contractorsApi.createIncident as any).mockResolvedValue({ id: "i2" });
});

describe("ContractorIncidentsTab", () => {
  it("lists incidents scoped by contractor", async () => {
    render(<ContractorIncidentsTab contractorId="c1" />);
    expect(await screen.findByText("падение")).toBeInTheDocument();
    expect(contractorsApi.listIncidents).toHaveBeenCalledWith({ contractor_id: "c1" });
  });

  it("registers an incident", async () => {
    render(<ContractorIncidentsTab contractorId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Зарегистрировать инцидент" }));
    fireEvent.change(await screen.findByLabelText("Тип инцидента"), { target: { value: "порез" } });
    fireEvent.change(screen.getByLabelText("Дата и время"), { target: { value: "2026-06-02T09:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(contractorsApi.createIncident).toHaveBeenCalledWith(
        expect.objectContaining({ contractor_id: "c1", incident_type: "порез", severity: "medium" })
      )
    );
  });
});
