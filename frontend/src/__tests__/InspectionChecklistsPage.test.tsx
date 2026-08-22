import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InspectionChecklistsPage from "@/pages/inspection-checklists/InspectionChecklistsPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getInspectionWorkspaceSnapshotMock = vi.fn();

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getInspectionWorkspaceSnapshot: (...args: unknown[]) =>
      getInspectionWorkspaceSnapshotMock(...args),
  },
}));

/**
 * Наполненный снимок: открытое предписание включает панель «Блокеры и
 * дальнейшие действия», проверки двух типов + предписание дают реестру
 * три строки («fire», «labor», «general») — на экране одновременно и
 * панель, и таблица.
 */
const populatedSnapshot = {
  inspections: [
    {
      id: "insp-1",
      authority: "МЧС",
      status: "scheduled",
      scheduled_at: "2020-01-01T00:00:00Z",
      inspection_type: "fire",
      purpose: "Плановая",
    },
    {
      id: "insp-2",
      authority: "ГИТ",
      status: "done",
      scheduled_at: "2020-02-01T00:00:00Z",
      inspection_type: "labor",
      purpose: "Внеплановая",
    },
  ],
  prescriptions: [{ id: "pres-1", status: "open", inspection_id: "insp-1" }],
  tasks: [{ id: "task-1", status: "open", overdue: true, entity_id: "insp-1" }],
  templates: [{ id: "tpl-1" }],
  packRuns: [],
};

describe("InspectionChecklistsPage", () => {
  beforeEach(() => {
    getInspectionWorkspaceSnapshotMock.mockReset();
  });

  it("рендерит панель блокеров и реестр типов проверок", async () => {
    getInspectionWorkspaceSnapshotMock.mockResolvedValue(populatedSnapshot);

    render(
      <MemoryRouter>
        <InspectionChecklistsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/блокеры и дальнейшие действия/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Чек-листы проверок")).toBeInTheDocument();
    expect(await screen.findByText("fire")).toBeInTheDocument();
    expect(screen.getByText("labor")).toBeInTheDocument();
    expect(screen.getByText("general")).toBeInTheDocument();
    expect(screen.getByText(/открытых предписаний: 1/i)).toBeInTheDocument();
  });

  // Приёмка UX-бюджета (ТЗ разд. 59.2, BIZ-60): меряем ОТРИСОВАННЫЙ
  // наполненный экран — панель блокеров и реестр видны одновременно.
  it("InspectionChecklistsPage в UX-бюджете", async () => {
    getInspectionWorkspaceSnapshotMock.mockResolvedValue(populatedSnapshot);

    render(
      <MemoryRouter>
        <InspectionChecklistsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/блокеры и дальнейшие действия/i),
    ).toBeInTheDocument();
    expect(await screen.findByText("fire")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "InspectionChecklistsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
