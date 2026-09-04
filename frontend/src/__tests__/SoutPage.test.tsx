import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const soutApiMock = vi.hoisted(() => ({
  list: vi.fn(),
  getReport: vi.fn(),
  getDeclaration: vi.fn(),
  listClassHistory: vi.fn(),
  getNormSuggestions: vi.fn(),
  previewCascade: vi.fn(),
  applyCascade: vi.fn(),
  linkWorkplacePosition: vi.fn(),
  linkFactorHazard: vi.fn(),
  downloadCard: vi.fn(),
  downloadSummary: vi.fn(),
  downloadDeclaration: vi.fn(),
  previewImport: vi.fn(),
  applyImport: vi.fn(),
}));

vi.mock("@/api/sout", () => ({
  soutApi: soutApiMock,
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import SoutPage from "@/pages/sout/SoutPage";

const campaign = {
  id: "camp-1",
  name: "Кампания №1",
  expert_org_name: "ООО Эксперт",
  report_number: "R-2026-01",
  report_date: "2026-02-01",
  status: "completed",
  planned_date: null,
  completed_date: "2026-02-01",
  created_at: "2026-01-10T00:00:00Z",
  updated_at: "2026-02-01T00:00:00Z",
};

const secondCampaign = {
  ...campaign,
  id: "camp-2",
  name: "Кампания №2",
  report_number: null,
  status: "draft",
};

const workplace = (id: string, code: string) => ({
  id,
  campaign_id: campaign.id,
  workplace_code: code,
  position_name: "Слесарь",
  person_id: null,
  assessed_class: "harmful_3_1",
  assessment_date: "2026-02-01",
  next_assessment_date: "2031-02-01",
  is_reassessment_due: false,
});

const report = {
  campaign,
  workplaces: [
    {
      workplace: workplace("wp-1", "РМ-001"),
      factors: [
        {
          id: "f-1",
          workplace_id: "wp-1",
          code: "4.1",
          name: "Шум",
          measured_class: "harmful_3_1",
          note: null,
        },
        {
          id: "f-2",
          workplace_id: "wp-1",
          code: "4.2",
          name: "Вибрация",
          measured_class: "acceptable",
          note: null,
        },
      ],
      guarantees: [
        { id: "g-1", workplace_id: "wp-1", kind: "extra_pay", detail: "4%" },
        { id: "g-2", workplace_id: "wp-1", kind: "medical_exam", detail: null },
      ],
    },
    {
      workplace: { ...workplace("wp-2", "РМ-002"), assessed_class: "optimal" },
      factors: [],
      guarantees: [],
    },
  ],
};

const declaration = {
  campaign_id: campaign.id,
  campaign_name: campaign.name,
  eligible: [],
  ineligible: [
    {
      workplace_code: "РМ-001",
      position_name: "Слесарь",
      assessed_class: "harmful_3_1",
      headcount: "1",
      report_ref: null,
      eligible: false,
      ineligible_reason: "класс 3.1",
    },
  ],
  eligible_count: 1,
  ineligible_count: 1,
};

describe("SoutPage", () => {
  beforeEach(() => {
    Object.values(soutApiMock).forEach((mock) => mock.mockReset());
    soutApiMock.list.mockResolvedValue({
      items: [campaign, secondCampaign],
      total: 2,
      limit: 100,
      offset: 0,
    });
    soutApiMock.getReport.mockResolvedValue(report);
    soutApiMock.getDeclaration.mockResolvedValue(declaration);
  });

  it("экран в UX-бюджете и списком, и с открытым отчётом кампании (BIZ-60)", async () => {
    // Меряем ДВА состояния: список кампаний и отчёт с рабочими местами —
    // повторяющиеся строки (LinkInput на каждое РМ и каждый фактор) видны
    // только во втором, замер одного списка ничего бы не доказал.
    await act(async () => {
      render(<SoutPage />);
    });
    expect(await screen.findByText("Кампания №1")).toBeInTheDocument();

    const listOnly = uxBudgetDelta(document.body, "SoutPage");
    expect(listOnly.unexpected).toEqual([]);
    expect(listOnly.stale).toEqual([]);

    await act(async () => {
      fireEvent.click(screen.getByText("Кампания №1"));
    });
    expect((await screen.findAllByText(/РМ-001/)).length).toBeGreaterThan(0);
    expect(soutApiMock.getReport).toHaveBeenCalledWith("camp-1");
    expect(screen.getByText(/Подлежат декларированию: 1/)).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "SoutPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
