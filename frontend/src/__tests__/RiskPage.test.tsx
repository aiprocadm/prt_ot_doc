import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RiskPage from "@/pages/risk/RiskPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const riskState = {
  listHazards: vi.fn(),
  listAssessments: vi.fn(),
  hazards: [
    { id: "haz-1", title: "Скользкий пол", description: "Влажное покрытие" },
  ],
  // Наполненные расчёты: настоящая таблица (не мок) должна показать строки,
  // иначе замер UX-бюджета мерил бы пустой экран.
  assessments: [
    {
      id: "as-1",
      company_id: "cmp-1",
      status: "draft",
      total_score: 12,
      hazards: [{ hazard_id: "haz-1", probability: 3, severity: 4 }],
      created_at: "2026-08-01T10:00:00Z",
      updated_at: "2026-08-02T10:00:00Z",
    },
    {
      id: "as-2",
      company_id: "cmp-1",
      status: "approved",
      total_score: 4,
      hazards: [{ hazard_id: "haz-1", probability: 2, severity: 2 }],
      created_at: "2026-08-01T10:00:00Z",
      updated_at: "2026-08-03T10:00:00Z",
    },
  ],
  loading: false,
  error: null,
  createAssessment: vi.fn(),
  exportAssessment: vi.fn(),
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
  // Таблица берёт стор селектором (state => state.items), форма — целиком:
  // мок обязан уметь оба вызова, как настоящий zustand-стор.
  useCompaniesStore: (selector?: (state: typeof companiesState) => unknown) =>
    selector ? selector(companiesState) : companiesState,
}));

vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => abilityState,
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
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(riskState.listHazards).toHaveBeenCalledTimes(1);
      expect(riskState.listAssessments).toHaveBeenCalledTimes(1);
      expect(companiesState.list).toHaveBeenCalledTimes(1);
    });
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    render(
      <MemoryRouter>
        <RiskPage />
      </MemoryRouter>,
    );

    // Наполненное состояние: справочник опасностей и НАСТОЯЩАЯ таблица
    // расчётов со строками из фикстур — замер пустого экрана это самообман.
    await screen.findAllByText("Скользкий пол");
    const table = await screen.findByRole("table");
    expect(table.textContent).toContain("Ромашка");

    const budget = uxBudgetDelta(document.body, "RiskPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
