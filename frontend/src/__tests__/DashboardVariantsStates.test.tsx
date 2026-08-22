import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ClientDeliveryDashboardPage from "@/pages/dashboard/ClientDeliveryDashboardPage";
import SafetyDashboardPage from "@/pages/dashboard/SafetyDashboardPage";
import TrainingDashboardPage from "@/pages/dashboard/TrainingDashboardPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

describe("Dashboard variants operational states", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("shows empty state on SafetyDashboardPage when API returns empty payload", async () => {
    getMock.mockResolvedValue({ data: {} });

    render(
      <MemoryRouter>
        <SafetyDashboardPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/данные дашборда отсутствуют/i),
    ).toBeInTheDocument();
  });

  it("shows loading state on TrainingDashboardPage while API call is pending", async () => {
    getMock.mockImplementation(() => new Promise(() => undefined));

    render(
      <MemoryRouter>
        <TrainingDashboardPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/загрузка дашборда/i)).toBeInTheDocument();
  });

  it("shows error state on ClientDeliveryDashboardPage when API fails", async () => {
    getMock.mockRejectedValue({
      status: 400,
      message: "dashboard load failed",
    });

    render(
      <MemoryRouter>
        <ClientDeliveryDashboardPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "dashboard load failed",
      );
    });
  });
});

describe("Dashboard variants UX budget (BIZ-60)", () => {
  // Форма живого ответа /analytics/dashboard/{safety,training,client-delivery}:
  // KpiDashboardService отдаёт { name, widgets: {…счётчики} } — меряем экран,
  // наполненный ровно тем, что он получает в бою, а не удобным моком.
  const filledPayload = (name: string) => ({
    name,
    widgets: {
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
    },
  });

  const cases = [
    ["SafetyDashboardPage", "safety", SafetyDashboardPage],
    ["TrainingDashboardPage", "training", TrainingDashboardPage],
    [
      "ClientDeliveryDashboardPage",
      "client-delivery",
      ClientDeliveryDashboardPage,
    ],
  ] as const;

  beforeEach(() => {
    getMock.mockReset();
  });

  it.each(cases)(
    "%s: наполненный экран в UX-бюджете",
    async (screenName, payloadName, Page) => {
      getMock.mockResolvedValue({ data: filledPayload(payloadName) });

      render(
        <MemoryRouter>
          <Page />
        </MemoryRouter>,
      );

      expect(await screen.findByText("Widgets")).toBeInTheDocument();

      const budget = uxBudgetDelta(document.body, screenName);
      expect(budget.unexpected).toEqual([]);
      expect(budget.stale).toEqual([]);
    },
  );
});
