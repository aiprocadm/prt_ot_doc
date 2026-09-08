import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const dashboardApiMock = vi.hoisted(() => ({ getByEndpoint: vi.fn() }));

vi.mock("@/api/dashboardApi", () => ({
  dashboardApiClient: {
    getByEndpoint: (...args: unknown[]) =>
      dashboardApiMock.getByEndpoint(...args),
  },
}));

import { DashboardApiPage } from "@/pages/dashboard/DashboardApiPage";

/**
 * Общий дашборд по адресу: на нём построены три экрана продукта (безопасность,
 * обучение, доставка клиенту). Замер бюджета делается ЗДЕСЬ — обёртки
 * отличаются только заголовком и адресом, и мерить их порознь значило бы
 * трижды измерить одну и ту же вёрстку.
 */
const payload = {
  total_incidents: 42,
  open_incidents: 7,
  closed_incidents: 35,
  avg_resolution_days: 3.4,
};

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <DashboardApiPage
          title="Дашборд безопасности"
          endpoint="/analytics/dashboard/safety"
        />
      </MemoryRouter>,
    );
  });
  expect(await screen.findByText("Total Incidents")).toBeInTheDocument();
};

describe("DashboardApiPage", () => {
  beforeEach(() => {
    dashboardApiMock.getByEndpoint.mockReset();
    dashboardApiMock.getByEndpoint.mockResolvedValue(payload);
  });

  it("показывает показатели по данным своего адреса", async () => {
    await renderPage();

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(dashboardApiMock.getByEndpoint).toHaveBeenCalledWith(
      "/analytics/dashboard/safety",
    );
  });

  it("пустой ответ — это «данных нет», а не пустая страница", async () => {
    dashboardApiMock.getByEndpoint.mockResolvedValue({});
    await act(async () => {
      render(
        <MemoryRouter>
          <DashboardApiPage title="Дашборд обучения" endpoint="/x" />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText("Данные дашборда отсутствуют"),
    ).toBeInTheDocument();
  });

  it("экран в UX-бюджете на наполненных данных", async () => {
    await renderPage();

    const budget = uxBudgetDelta(document.body, "DashboardApiPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
