import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FireInspectionsPage from "@/pages/fire-inspections/FireInspectionsPage";
import FireTrainingPage from "@/pages/fire-training/FireTrainingPage";
import InspectionPrepPackagesPage from "@/pages/inspection-prep/InspectionPrepPackagesPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getInspectionWorkspaceSnapshotMock = vi.fn();
const getFireTrainingSnapshotMock = vi.fn();
const listDrillsMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getInspectionWorkspaceSnapshot: (...args: unknown[]) =>
      getInspectionWorkspaceSnapshotMock(...args),
    getFireTrainingSnapshot: (...args: unknown[]) =>
      getFireTrainingSnapshotMock(...args),
  },
}));

vi.mock("@/api/fireSafety", () => ({
  fireSafetyApi: {
    listDrills: (...args: unknown[]) => listDrillsMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

/** Сводка готовности без тренировок — исходное состояние арендатора. */
const emptyReadiness = {
  total_units: 0,
  overdue_recharge: 0,
  overdue_inspection: 0,
  due_soon: 0,
  due_soon_days: 30,
  overdue_fire_briefings: 0,
  overdue_drills: 0,
  planned_drills: 0,
  last_drill_on: null,
  days_since_last_drill: null,
};

/** Наполненный снимок: и панель блокеров, и таблица реестра на экране. */
const populatedWorkspaceSnapshot = {
  inspections: [
    {
      id: "insp-1",
      authority: "МЧС",
      status: "scheduled",
      scheduled_at: "2020-01-01T00:00:00Z",
      inspection_type: "fire",
      purpose: "Плановая",
    },
  ],
  prescriptions: [{ id: "pres-1", status: "open", inspection_id: "insp-1" }],
  tasks: [{ id: "task-1", status: "open", overdue: true, entity_id: "insp-1" }],
  templates: [{ id: "tpl-1" }],
  packRuns: [],
};

/** Наполненный снимок инструктажей: панель блокеров + все три карточки. */
const populatedFireTrainingSnapshot = {
  templates: [{ id: "tpl-1", title: "Template", status: "active" }],
  journals: [{ id: "jr-1", title: "Journal", status: "active" }],
  overdueEntries: [{ id: "ov-1", briefing_type: "repeat", status: "overdue" }],
  programs: [{ id: "prg-1", title: "Program", status: "active" }],
};

/** Просроченная тренировка: план прошёл, протокола нет. */
const populatedDrill = {
  id: "drill-1",
  kind: "evacuation",
  kind_label: "Тренировка по эвакуации",
  title: "Тренировка по эвакуации, корпус А",
  planned_on: "2026-08-01",
  held_on: null,
  site_id: null,
  scenario: "Возгорание в электрощитовой",
  participants: null,
  outcome: null,
  outcome_label: null,
  findings: null,
  status: "overdue",
};

describe("Inspection/fire next actions", () => {
  beforeEach(() => {
    getInspectionWorkspaceSnapshotMock.mockReset();
    getFireTrainingSnapshotMock.mockReset();
    listDrillsMock.mockReset();
    readinessMock.mockReset();
    listDrillsMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue(emptyReadiness);
  });

  it("shows blockers panel on FireInspectionsPage", async () => {
    getInspectionWorkspaceSnapshotMock.mockResolvedValue({
      inspections: [
        {
          id: "insp-1",
          authority: "МЧС",
          status: "scheduled",
          scheduled_at: "2020-01-01T00:00:00Z",
          inspection_type: "fire",
          purpose: "Плановая",
        },
      ],
      prescriptions: [
        { id: "pres-1", status: "open", inspection_id: "insp-1" },
      ],
      tasks: [
        { id: "task-1", status: "open", overdue: true, entity_id: "insp-1" },
      ],
      templates: [],
      packRuns: [],
    });

    render(
      <MemoryRouter>
        <FireInspectionsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/блокеры и дальнейшие действия/i),
    ).toBeInTheDocument();
  });

  it("shows overdue-training next actions on FireTrainingPage", async () => {
    getFireTrainingSnapshotMock.mockResolvedValue({
      templates: [{ id: "tpl-1", title: "Template", status: "active" }],
      journals: [{ id: "jr-1", title: "Journal", status: "active" }],
      overdueEntries: [
        { id: "ov-1", briefing_type: "repeat", status: "overdue" },
      ],
      programs: [],
    });

    render(
      <MemoryRouter>
        <FireTrainingPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/блокеры и дальнейшие действия/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/просроченных записей инструктажей/i),
    ).toBeInTheDocument();
  });

  it("shows prep-packages blockers panel", async () => {
    getInspectionWorkspaceSnapshotMock.mockResolvedValue({
      inspections: [
        { id: "insp-1", authority: "Ростехнадзор", status: "open" },
      ],
      prescriptions: [
        { id: "pres-1", inspection_id: "insp-1", status: "open" },
      ],
      tasks: [{ id: "task-1", entity_id: "insp-1", status: "open" }],
      templates: [{ id: "tpl-1" }],
      packRuns: [],
    });

    render(
      <MemoryRouter>
        <InspectionPrepPackagesPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/блокеры и дальнейшие действия/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/открытых ограничений по предписаниям/i),
    ).toBeInTheDocument();
  });

  // Приёмка UX-бюджета (ТЗ разд. 59.2, BIZ-60): меряем ОТРИСОВАННЫЙ
  // наполненный экран — панель блокеров, статистика и реестр видны.

  it("FireInspectionsPage в UX-бюджете", async () => {
    getInspectionWorkspaceSnapshotMock.mockResolvedValue(
      populatedWorkspaceSnapshot,
    );

    render(
      <MemoryRouter>
        <FireInspectionsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/блокеры и дальнейшие действия/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/проверки пожарной безопасности/i),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "FireInspectionsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("FireTrainingPage в UX-бюджете", async () => {
    getFireTrainingSnapshotMock.mockResolvedValue(
      populatedFireTrainingSnapshot,
    );
    listDrillsMock.mockResolvedValue([populatedDrill]);
    readinessMock.mockResolvedValue({
      ...emptyReadiness,
      overdue_drills: 1,
      planned_drills: 2,
      last_drill_on: "2026-08-01",
      days_since_last_drill: 23,
    });

    render(
      <MemoryRouter>
        <FireTrainingPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/блокеры и дальнейшие действия/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/план-график тренировок и учений/i),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "FireTrainingPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  // Доп. №1 разд. 54.1 «Тренировки и учения». Экран назывался «инструктажи и
  // учения», а учений не показывал НИ ОДНОГО — сущности тренировки не было.
  it("FireTrainingPage показывает план-график тренировок", async () => {
    getFireTrainingSnapshotMock.mockResolvedValue(
      populatedFireTrainingSnapshot,
    );
    listDrillsMock.mockResolvedValue([populatedDrill]);
    readinessMock.mockResolvedValue({
      ...emptyReadiness,
      planned_drills: 1,
      last_drill_on: "2026-08-01",
      days_since_last_drill: 23,
    });

    render(
      <MemoryRouter>
        <FireTrainingPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/тренировка по эвакуации, корпус а/i),
    ).toBeInTheDocument();
    // Состояние — словами, а не кодом «overdue».
    expect(screen.getByText("Просрочена")).toBeInTheDocument();
  });

  it("FireTrainingPage не выдаёт интервал полгода за нарушение", async () => {
    // Граница названа НА ЭКРАНЕ: применимость нормы ППР из данных площадки не
    // следует, поэтому платформа сообщает факт, а вывод делает специалист.
    getFireTrainingSnapshotMock.mockResolvedValue(
      populatedFireTrainingSnapshot,
    );
    readinessMock.mockResolvedValue({
      ...emptyReadiness,
      last_drill_on: "2025-08-01",
      days_since_last_drill: 388,
    });

    render(
      <MemoryRouter>
        <FireTrainingPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/применимость определяет специалист/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/388 дн. назад/)).toBeInTheDocument();
  });

  it("FireTrainingPage переключается на инструктажи", async () => {
    getFireTrainingSnapshotMock.mockResolvedValue(
      populatedFireTrainingSnapshot,
    );

    render(
      <MemoryRouter>
        <FireTrainingPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Инструктажи" }));
    expect(screen.getByText(/просроченные записи/i)).toBeInTheDocument();
  });

  it("InspectionPrepPackagesPage в UX-бюджете", async () => {
    getInspectionWorkspaceSnapshotMock.mockResolvedValue(
      populatedWorkspaceSnapshot,
    );

    render(
      <MemoryRouter>
        <InspectionPrepPackagesPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/блокеры и дальнейшие действия/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/пакеты подготовки к проверкам/i),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "InspectionPrepPackagesPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
