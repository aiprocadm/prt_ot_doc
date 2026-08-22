import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const operationsApiMock = vi.hoisted(() => ({
  getActivitiesSnapshot: vi.fn(),
}));

vi.mock("@/api/operations", () => ({ operationsApi: operationsApiMock }));

import ActivitiesPage from "@/pages/activities/ActivitiesPage";

const snapshot = {
  tasks: [
    {
      id: "task-1",
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z",
      title: "Проверить замену огнетушителей",
      description: null,
      entity_type: "corrective_action",
      entity_id: "ca-1",
      due_at: "2026-08-30T00:00:00Z",
      status: "open" as const,
      assignee_id: null,
      created_by: null,
      priority: "high" as const,
      next_remind_at: null,
      reminder_channel: null,
      completed_at: null,
      overdue: true,
    },
    {
      id: "task-2",
      created_at: "2026-08-02T00:00:00Z",
      updated_at: "2026-08-02T00:00:00Z",
      title: "Закрытая задача без привязки",
      description: null,
      entity_type: "corrective_action",
      entity_id: "unrelated-entity",
      due_at: null,
      status: "done" as const,
      assignee_id: null,
      created_by: null,
      priority: "medium" as const,
      next_remind_at: null,
      reminder_channel: null,
      completed_at: "2026-08-10T00:00:00Z",
      overdue: false,
    },
  ],
  correctiveActions: [
    {
      id: "ca-1",
      title: "Заменить огнетушители в цехе",
      status: "in_progress",
      source_type: "inspection",
      source_id: "insp-1",
      action_type: "corrective",
      due_date: "2026-09-01T00:00:00Z",
      responsible_user_id: null,
      site_id: null,
      effectiveness_status: null,
      description: null,
      completed_at: null,
    },
    {
      id: "ca-2",
      title: "Провести внеплановый инструктаж",
      status: "open",
      source_type: "incident",
      source_id: "inc-1",
      action_type: "preventive",
      due_date: "2026-09-15T00:00:00Z",
      responsible_user_id: null,
      site_id: null,
      effectiveness_status: null,
      description: null,
      completed_at: null,
    },
  ],
};

describe("ActivitiesPage", () => {
  beforeEach(() => {
    operationsApiMock.getActivitiesSnapshot.mockReset();
    operationsApiMock.getActivitiesSnapshot.mockResolvedValue(snapshot);
  });

  it("рендерит реестр мероприятий из живого снапшота", async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <ActivitiesPage />
        </MemoryRouter>,
      );
    });

    expect(
      await screen.findByText("Заменить огнетушители в цехе"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Провести внеплановый инструктаж"),
    ).toBeInTheDocument();
    // Колонка «Связанная задача»: ca-1 связан по entity_id, ca-2 — нет («—»).
    expect(
      screen.getByText("Проверить замену огнетушителей"),
    ).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(operationsApiMock.getActivitiesSnapshot).toHaveBeenCalledTimes(1);
  });

  it("экран в UX-бюджете на наполненных данных (BIZ-60)", async () => {
    await act(async () => {
      render(
        <MemoryRouter>
          <ActivitiesPage />
        </MemoryRouter>,
      );
    });
    expect(
      await screen.findByText("Заменить огнетушители в цехе"),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "ActivitiesPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
