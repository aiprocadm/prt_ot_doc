import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getAttentionMock = vi.hoisted(() => vi.fn());

vi.mock("@/api/workspace", () => ({
  workspaceApi: {
    getAttention: (...args: unknown[]) => getAttentionMock(...args),
  },
}));

// Все виджеты «Фокус OT/ПБ» видны только при полном наборе прав — меряем
// бюджет худшего (самого наполненного) случая, а не урезанного по ролям.
vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => ({ can: () => true }),
}));

import WorkspaceAttentionPage from "@/pages/workspace/WorkspaceAttentionPage";

/** Наполненный ответ: summary с ненулевыми счётчиками, записи, дисциплины,
 *  блокеры и рекомендации — чтобы панель отрисовала ВСЕ свои секции разом. */
const filledAttention = () => ({
  generated_at: "2026-08-22T00:00:00Z",
  summary: {
    overdue_tasks: 2,
    due_soon_tasks: 1,
    overdue_deadlines: 1,
    pending_sync_batches: 1,
    failed_sync_batches: 1,
    readiness_blockers: 1,
  },
  items: [
    {
      item_type: "medical_exam",
      id: "medical_exam:e1",
      severity: "critical",
      title: "Медосмотр: Иванов И.И.",
      status: "overdue",
      due_at: "2026-07-01T00:00:00Z",
      entity_type: "medical_exam",
      entity_id: "e1",
      reason: "Срок прошёл",
      discipline: "medical",
    },
    {
      item_type: "task",
      id: "t1",
      severity: "high",
      title: "Просроченная задача по обучению",
      status: "open",
      due_at: "2026-07-02T00:00:00Z",
      entity_type: null,
      entity_id: null,
      reason: "Задача просрочена",
      discipline: null,
    },
  ],
  blockers: [
    {
      code: "employees_missing_medical",
      title: "Сотрудники без медосмотра",
      severity: "critical",
      count: 4,
      reason: "Есть сотрудники с истекшим или отсутствующим медосмотром",
      entity_type: "person",
      action_hint: "Откройте реестр сотрудников и назначьте медосмотр",
    },
  ],
  recommendations: ["Закрыть просроченные задачи по обучению"],
  disciplines: [
    {
      code: "medical",
      title: "Медосмотры",
      measured: true,
      overdue: 1,
      due_soon: 0,
      reason: null,
    },
  ],
});

describe("WorkspaceAttentionPage", () => {
  beforeEach(() => {
    getAttentionMock.mockReset();
    getAttentionMock.mockResolvedValue(filledAttention());
  });

  it("рисует сводку, записи внимания и статичные виджеты фокуса", async () => {
    render(
      <MemoryRouter>
        <WorkspaceAttentionPage />
      </MemoryRouter>,
    );

    // Ждём именно данные API: заголовок страницы статичен и появляется
    // ДО ответа getAttention — синхронные getBy* дали бы гонку.
    expect(await screen.findByText("2 просроченных задач")).toBeInTheDocument();
    expect(screen.getByText("Медосмотр: Иванов И.И.")).toBeInTheDocument();
    expect(screen.getByText("Сотрудники без медосмотра")).toBeInTheDocument();
    expect(
      screen.getByText("Закрыть просроченные задачи по обучению"),
    ).toBeInTheDocument();
    expect(getAttentionMock).toHaveBeenCalledWith(20);

    // Статичные секции экрана: фокус-виджеты по правам и быстрые переходы.
    expect(screen.getByText("Просроченное обучение")).toBeInTheDocument();
    expect(screen.getByText("Истечения медосмотров")).toBeInTheDocument();
    expect(screen.getByText("Задачи и сроки")).toBeInTheDocument();
  });

  it("экран в UX-бюджете на наполненных данных (BIZ-60 волна 5)", async () => {
    render(
      <MemoryRouter>
        <WorkspaceAttentionPage />
      </MemoryRouter>,
    );

    // Меряем ОТРИСОВАННЫЙ наполненный экран: пустой замер до ответа API
    // ничего не доказал бы.
    expect(await screen.findByText("2 просроченных задач")).toBeInTheDocument();
    expect(screen.getByText("Медосмотр: Иванов И.И.")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "WorkspaceAttentionPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
