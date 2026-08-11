import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { ContractorEmployeesTab } from "./ContractorEmployeesTab";
import { contractorsApi } from "@/api/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      listEmployees: vi.fn(),
      createEmployee: vi.fn(),
      getEmployeeReadiness: vi.fn(),
      getEmployeeChecklist: vi.fn(),
      admitEmployee: vi.fn()
    }
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function" ? (children as (v: boolean) => unknown)(true) : children
}));

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.listEmployees as any).mockResolvedValue({
    items: [
      { id: "e1", contractor_id: "c1", full_name: "Сидоров С.С.", position: "Монтажник", access_status: "pending", training_status: "valid", medical_status: "valid" }
    ],
    total: 1
  });
  (contractorsApi.createEmployee as any).mockResolvedValue({ id: "e2" });
});

describe("ContractorEmployeesTab", () => {
  it("lists employees scoped by contractor", async () => {
    render(<ContractorEmployeesTab contractorId="c1" onChanged={() => undefined} />);
    expect(await screen.findByText("Сидоров С.С.")).toBeInTheDocument();
    expect(contractorsApi.listEmployees).toHaveBeenCalledWith({ contractor_id: "c1" });
  });

  it("creates an employee for the contractor", async () => {
    render(<ContractorEmployeesTab contractorId="c1" onChanged={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Добавить сотрудника" }));
    fireEvent.change(await screen.findByLabelText("ФИО"), { target: { value: "Новый Н.Н." } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(contractorsApi.createEmployee).toHaveBeenCalledWith(
        expect.objectContaining({ contractor_id: "c1", full_name: "Новый Н.Н." })
      )
    );
  });
});
