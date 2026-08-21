import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminPage from "@/pages/admin/AdminPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getAdminSnapshotMock = vi.fn();

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getAdminSnapshot: (...args: unknown[]) => getAdminSnapshotMock(...args),
  },
}));

vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => ({
    can: () => true,
  }),
}));

describe("AdminPage", () => {
  beforeEach(() => {
    getAdminSnapshotMock.mockReset();
  });

  it("renders enterprise diagnostics widgets from live snapshot", async () => {
    getAdminSnapshotMock.mockResolvedValue({
      tenancy: { tenant: { id: "tenant-1", slug: "corp" } },
      outbox: [
        { id: "o1", event_type: "doc.created", status: "pending", attempts: 1 },
      ],
      webhooks: [],
      apiTokens: [],
      auditItems: [],
      integrationReadiness: null,
      attention: null,
      taskInbox: null,
      providerStatus: {
        production_ready: false,
        blocking_for_golive: ["signing"],
        providers: [
          {
            name: "signing",
            mode: "non_production",
            adapter: "internal-fallback",
          },
        ],
      },
      tenantHealth: {
        score: 88,
        grade: "B",
        failed_jobs_last24h: 1,
        outbox_events_poisoned: 0,
      },
      roleSummary: {
        role: "admin",
        open_tasks: 5,
        overdue_tasks: 2,
        overdue_deadlines: 1,
      },
    });

    render(
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Оценка здоровья тенанта"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Балл: 88 \/ 100/)).toBeInTheDocument();
    expect(screen.getByText(/Роль: admin/)).toBeInTheDocument();
    expect(screen.getByText(/Блокирующих провайдеров: 1/)).toBeInTheDocument();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    // Свои моки с наполненными данными: замер пустого экрана — самообман.
    getAdminSnapshotMock.mockResolvedValue({
      tenancy: { tenant: { id: "tenant-1", slug: "corp" } },
      outbox: [
        { id: "o1", event_type: "doc.created", status: "pending", attempts: 1 },
        { id: "o2", event_type: "doc.signed", status: "poisoned", attempts: 5 },
      ],
      webhooks: [
        { id: "w1", code: "crm-sync", is_active: true },
        { id: "w2", code: null, is_active: false },
      ],
      apiTokens: [{ id: "t1", name: "ci-token" }],
      auditItems: [
        { id: "a1", action: "create", object_type: "document" },
        { id: "a2", action: "update", object_type: "task" },
      ],
      integrationReadiness: {
        summary: {
          configured_total: 4,
          production_ready_total: 2,
          non_production_total: 2,
        },
        webhooks: { delivery_failed_total: 1 },
      },
      attention: {
        summary: {
          overdue_tasks: 3,
          due_soon_tasks: 2,
          overdue_deadlines: 1,
          readiness_blockers: 1,
        },
        recommendations: ["Проверить подпись", "Закрыть просроченные задачи"],
      },
      taskInbox: {
        total: 4,
        overdue: 2,
        items: [
          { id: "task-1", title: "Продлить обучение", priority: "high", overdue: true },
          { id: "task-2", title: "Выдать СИЗ", priority: "normal", overdue: false },
        ],
      },
      providerStatus: {
        production_ready: false,
        blocking_for_golive: ["signing"],
        providers: [
          {
            name: "signing",
            mode: "non_production",
            adapter: "internal-fallback",
          },
        ],
      },
      tenantHealth: {
        score: 88,
        grade: "B",
        failed_jobs_last24h: 1,
        outbox_events_poisoned: 0,
      },
      roleSummary: {
        role: "admin",
        open_tasks: 5,
        overdue_tasks: 2,
        overdue_deadlines: 1,
      },
    });

    render(
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>,
    );

    // Дожидаемся наполненного состояния всех блоков, а не заглушек загрузки.
    expect(
      await screen.findByText("Оценка здоровья тенанта"),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Всего открытых: 4/)).toBeInTheDocument();
    expect(await screen.findByText(/Настроено: 4/)).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "AdminPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
