import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { RiskAssessmentForm } from "@/features/risk/RiskAssessmentForm";

const riskState = {
  hazards: [{ id: "haz-1", title: "Скользкий пол" }],
  createAssessment: vi.fn(),
};

const companiesState = {
  items: [{ id: "cmp-1", name: "Ромашка" }],
  list: vi.fn(),
};

const abilityState = {
  can: vi.fn(),
};

vi.mock("@/stores/risk", () => ({
  useRiskStore: () => riskState,
}));

vi.mock("@/stores/companies", () => ({
  useCompaniesStore: () => companiesState,
}));

vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => abilityState,
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

describe("RiskAssessmentForm", () => {
  beforeEach(() => {
    riskState.createAssessment.mockReset();
    companiesState.list.mockReset();
    abilityState.can.mockReset();
    abilityState.can.mockImplementation(() => true);
    vi.mocked(toast.success).mockReset();
    vi.mocked(toast.error).mockReset();
  });

  it("shows toast error and keeps form data when save fails", async () => {
    riskState.createAssessment.mockRejectedValueOnce(new Error("save failed"));

    render(<RiskAssessmentForm />);

    fireEvent.change(screen.getByLabelText("Компания"), {
      target: { value: "cmp-1" },
    });
    fireEvent.change(screen.getByLabelText("Добавить опасность"), {
      target: { value: "haz-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить расчёт" }));

    await waitFor(() => {
      expect(riskState.createAssessment).toHaveBeenCalledWith({
        company_id: "cmp-1",
        hazards: [
          {
            hazard_id: "haz-1",
            probability: 1,
            severity: 1,
            mitigations: "",
          },
        ],
      });
    });
    expect(toast.error).toHaveBeenCalledWith("save failed");
    expect(screen.getByLabelText("Компания")).toHaveValue("cmp-1");
    expect(screen.getByRole("button", { name: "Удалить" })).toBeInTheDocument();
  });
});
