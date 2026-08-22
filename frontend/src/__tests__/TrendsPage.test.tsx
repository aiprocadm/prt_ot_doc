import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";
import { MemoryRouter } from "react-router-dom";

const dashboardApiMock = vi.hoisted(() => ({
  getByEndpoint: vi.fn(),
}));

vi.mock("@/api/dashboardApi", () => ({
  dashboardApiClient: {
    getByEndpoint: (...args: unknown[]) =>
      dashboardApiMock.getByEndpoint(...args),
  },
}));

import TrendsPage from "@/pages/analytics/TrendsPage";

// Наполненный ответ /analytics/trends/incidents: каждая пара ключ-значение
// становится KPI-карточкой в JsonKpiGrid.
const trendsPayload = {
  total_incidents: 42,
  open_incidents: 7,
  closed_incidents: 35,
  avg_resolution_days: 3.4,
};

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <TrendsPage />
      </MemoryRouter>,
    );
  });
  // Дожидаемся наполненного экрана: карточки KPI построены из ответа API.
  expect(await screen.findByText("Total Incidents")).toBeInTheDocument();
};

describe("TrendsPage", () => {
  beforeEach(() => {
    dashboardApiMock.getByEndpoint.mockReset();
    dashboardApiMock.getByEndpoint.mockResolvedValue(trendsPayload);
  });

  it("рендерит наполненный дашборд трендов по данным API", async () => {
    await renderPage();

    expect(screen.getByText("Тренды аналитики")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("Avg Resolution Days")).toBeInTheDocument();
    expect(screen.getByText("3.4")).toBeInTheDocument();
    expect(dashboardApiMock.getByEndpoint).toHaveBeenCalledWith(
      "/analytics/trends/incidents",
    );
  });

  it("экран в UX-бюджете на наполненных данных (BIZ-60 волна 5)", async () => {
    await renderPage();

    const budget = uxBudgetDelta(document.body, "TrendsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
