import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ExecutiveDashboardPage from "@/pages/dashboard/ExecutiveDashboardPage";
import PpeDashboardPage from "@/pages/dashboard/PpeDashboardPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

// Счётчики в том же наборе, что отдаёт AnalyticsAggregationService.base_counters
// в бою, — экран меряем наполненным ровно тем, что он получает от бэкенда.
const baseCounters = {
  trainings_overdue: 3,
  ppe_overdue: 1,
  incidents_open: 2,
  inspections_open: 4,
  prescriptions_overdue: 0,
  workflow_open: 5,
  workflow_sla_breached: 1,
  plan_tasks_overdue: 2,
  integration_errors: 0,
  edo_status_changes: 6,
  failed_notifications: 1,
};

// Форма живого ответа /analytics/dashboard/executive: роут добавляет к
// KPI-снапшоту дату и полезную нагрузку KpiDashboardService.executive —
// три ключа верхнего уровня, а не { name, widgets } как у остальных.
const executivePayload = {
  snapshot_date: "2026-08-22",
  widgets: baseCounters,
  dashboard: { name: "executive", widgets: baseCounters },
};

// Форма живого ответа /analytics/dashboard/ppe (KpiDashboardService.ppe).
const ppePayload = { name: "ppe", widgets: baseCounters };

describe("Executive/PPE dashboards: наполненный экран в UX-бюджете (BIZ-60)", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("ExecutiveDashboardPage: рендер с данными и приёмка бюджета", async () => {
    getMock.mockResolvedValue({ data: executivePayload });

    render(
      <MemoryRouter>
        <ExecutiveDashboardPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Snapshot Date")).toBeInTheDocument();
    expect(screen.getByText("Widgets")).toBeInTheDocument();
    expect(screen.getByText("Стратегический дашборд")).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith("/analytics/dashboard/executive");

    const budget = uxBudgetDelta(document.body, "ExecutiveDashboardPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("PpeDashboardPage: рендер с данными и приёмка бюджета", async () => {
    getMock.mockResolvedValue({ data: ppePayload });

    render(
      <MemoryRouter>
        <PpeDashboardPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Widgets")).toBeInTheDocument();
    expect(screen.getByText("Дашборд СИЗ")).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith("/analytics/dashboard/ppe");

    const budget = uxBudgetDelta(document.body, "PpeDashboardPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
