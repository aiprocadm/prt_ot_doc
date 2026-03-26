import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RiskPage from "@/pages/risk/RiskPage";

const riskState = {
  listHazards: vi.fn(),
  listAssessments: vi.fn(),
  hazards: [{ id: "haz-1", title: "Скользкий пол", description: "Влажное покрытие" }],
  assessments: [],
  loading: false,
  error: null,
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

vi.mock("@/features/risk/RiskAssessmentsTable", () => ({
  RiskAssessmentsTable: () => <div>risk assessments table</div>,
}));

describe("RiskPage", () => {
  beforeEach(() => {
    riskState.listHazards.mockReset();
    riskState.listAssessments.mockReset();
    companiesState.list.mockReset();
    abilityState.can.mockReset();
    abilityState.can.mockImplementation(() => true);
  });

  it("loads hazards only once while still loading assessments and companies", async () => {
    render(
      <MemoryRouter>
        <RiskPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(riskState.listHazards).toHaveBeenCalledTimes(1);
      expect(riskState.listAssessments).toHaveBeenCalledTimes(1);
      expect(companiesState.list).toHaveBeenCalledTimes(1);
    });
  });
});