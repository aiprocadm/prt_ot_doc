import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { EmployeeAdmissionDialog } from "./EmployeeAdmissionDialog";
import { contractorsApi } from "@/api/contractors";
import { Button } from "@/components/ui/button";
import type { ContractorEmployee } from "@/types/dto/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      getEmployeeReadiness: vi.fn(),
      getEmployeeChecklist: vi.fn(),
      admitEmployee: vi.fn()
    }
  };
});

const employee: ContractorEmployee = {
  id: "e1",
  contractor_id: "c1",
  full_name: "Сидоров С.С.",
  access_status: "pending",
  training_status: "valid",
  medical_status: "valid"
};

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.getEmployeeReadiness as any).mockResolvedValue({ employee_id: "e1", status: "warning", violations: [], warnings: ["Медосмотр истекает"] });
  (contractorsApi.getEmployeeChecklist as any).mockResolvedValue({
    employee_id: "e1",
    items: [{ doc_type: "medical_cert", scope: "employee", mandatory: true, status: "due_soon", satisfied_by: null }]
  });
});

const open = async () => {
  render(<EmployeeAdmissionDialog employee={employee} trigger={<Button>Допуск</Button>} onAdmitted={() => undefined} />);
  fireEvent.click(screen.getByRole("button", { name: "Допуск" }));
};

describe("EmployeeAdmissionDialog", () => {
  it("loads readiness and checklist on open", async () => {
    await open();
    await waitFor(() => expect(contractorsApi.getEmployeeReadiness).toHaveBeenCalledWith("e1"));
    expect(contractorsApi.getEmployeeChecklist).toHaveBeenCalledWith("e1");
    expect(await screen.findByText("Медосмотр истекает")).toBeInTheDocument();
  });

  it("admits successfully with a warning verdict", async () => {
    (contractorsApi.admitEmployee as any).mockResolvedValue({ employee_id: "e1", status: "warning", violations: [], warnings: ["ок с замечаниями"] });
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Допустить" }));
    await waitFor(() => expect(contractorsApi.admitEmployee).toHaveBeenCalledWith("e1"));
    expect(await screen.findByText(/Допущен с замечаниями/)).toBeInTheDocument();
  });

  it("shows violations when admit is blocked (409)", async () => {
    (contractorsApi.admitEmployee as any).mockRejectedValue({
      status: 409,
      code: "requirements_not_met",
      message: "not cleared",
      details: { details: [{ employee_id: "e1", violations: ["Нет лицензии", "Просрочен медосмотр"] }] }
    });
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Допустить" }));
    expect(await screen.findByText("Нет лицензии")).toBeInTheDocument();
    expect(screen.getByText("Просрочен медосмотр")).toBeInTheDocument();
  });
});
