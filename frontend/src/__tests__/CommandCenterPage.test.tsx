import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const operationalDashboardApiMock = vi.hoisted(() => ({
  getDashboard: vi.fn(),
}));

vi.mock("@/api/operationalDashboard", () => ({
  operationalDashboardApi: {
    getDashboard: (...args: unknown[]) =>
      operationalDashboardApiMock.getDashboard(...args),
  },
}));

import type { OperationalDashboardDto } from "@/api/operationalDashboard";
import CommandCenterPage from "@/pages/operational/CommandCenterPage";
import { useOperationalDashboardStore } from "@/stores/operationalDashboard";

/**
 * Наполненный ответ агрегатора: четыре категории всех уровней важности,
 * у части алертов есть внутренняя ссылка «Перейти» — экран рисует и сводку
 * по важности, и карточки категорий, и строки со ссылками.
 */
const dashboard: OperationalDashboardDto = {
  tenant_id: "tenant-1",
  status: "critical",
  timestamp: "2026-08-22T00:00:00Z",
  health_status: "ok",
  alert_count: { critical: 1, high: 2, medium: 1, low: 1 },
  alerts: [
    {
      id: "a1",
      category: "high_risk",
      severity: "critical",
      title: "Критический риск на объекте",
      description: "PxS выше порога",
      count: 3,
      action_url: "/risk",
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-08-22T00:00:00Z",
      expires_at: null,
    },
    {
      id: "a2",
      category: "overdue",
      severity: "high",
      title: "Просроченные обучения",
      description: null,
      count: 5,
      action_url: "/training",
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-08-22T00:00:00Z",
      expires_at: null,
    },
    {
      id: "a3",
      category: "integration_error",
      severity: "high",
      title: "Сбой интеграции 1С",
      description: null,
      count: 1,
      action_url: null,
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-08-22T00:00:00Z",
      expires_at: null,
    },
    {
      id: "a4",
      category: "data_quality",
      severity: "medium",
      title: "Пробелы в данных сотрудников",
      description: "Нет СНИЛС у части сотрудников",
      count: 7,
      action_url: "/staff",
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-08-22T00:00:00Z",
      expires_at: null,
    },
    {
      id: "a5",
      category: "unassigned_task",
      severity: "low",
      title: "Неназначенные задачи",
      description: null,
      count: 2,
      action_url: null,
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-08-22T00:00:00Z",
      expires_at: null,
    },
  ],
};

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <CommandCenterPage />
      </MemoryRouter>,
    );
  });
};

describe("CommandCenterPage", () => {
  beforeEach(() => {
    operationalDashboardApiMock.getDashboard.mockReset();
    operationalDashboardApiMock.getDashboard.mockResolvedValue(dashboard);
    // Стор глобальный — между тестами возвращаем его к чистому состоянию,
    // иначе данные прошлого теста маскируют незагрузившийся экран.
    useOperationalDashboardStore.setState({
      data: null,
      loading: false,
      error: null,
    });
  });

  it("загружает дашборд через API и рисует наполненный экран", async () => {
    await renderPage();

    // Дожидаемся именно ДАННЫХ, а не каркаса: заголовки алертов приходят
    // только из ответа замоканного API.
    expect(
      await screen.findByText("Критический риск на объекте"),
    ).toBeInTheDocument();
    expect(screen.getByText("Просроченные обучения")).toBeInTheDocument();
    expect(screen.getByText("Сбой интеграции 1С")).toBeInTheDocument();
    expect(operationalDashboardApiMock.getDashboard).toHaveBeenCalledTimes(1);

    // Карточки категорий с русскими подписями и сводка по важности.
    expect(screen.getByText("Высокий риск")).toBeInTheDocument();
    expect(screen.getByText("Качество данных")).toBeInTheDocument();
    expect(screen.getByText("Критичные: 1")).toBeInTheDocument();
    // Хлебная крошка и общий статус.
    expect(
      screen.getByRole("navigation", { name: "Навигационная цепочка" }),
    ).toHaveTextContent("Командный центр");
    expect(screen.getByText("Критично")).toBeInTheDocument();
  });

  it("экран в UX-бюджете (BIZ-60 волна 5)", async () => {
    await renderPage();
    expect(
      await screen.findByText("Критический риск на объекте"),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "CommandCenterPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("кнопка «Обновить» перезапрашивает дашборд", async () => {
    const user = userEvent.setup();
    await renderPage();
    expect(
      await screen.findByText("Критический риск на объекте"),
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /Обновить/ }));
    });

    expect(operationalDashboardApiMock.getDashboard).toHaveBeenCalledTimes(2);
  });
});
