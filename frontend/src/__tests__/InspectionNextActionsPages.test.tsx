import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FireInspectionsPage from "@/pages/fire-inspections/FireInspectionsPage";
import FireTrainingPage from "@/pages/fire-training/FireTrainingPage";
import InspectionPrepPackagesPage from "@/pages/inspection-prep/InspectionPrepPackagesPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getInspectionWorkspaceSnapshotMock = vi.fn();
const getFireTrainingSnapshotMock = vi.fn();

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getInspectionWorkspaceSnapshot: (...args: unknown[]) =>
      getInspectionWorkspaceSnapshotMock(...args),
    getFireTrainingSnapshot: (...args: unknown[]) =>
      getFireTrainingSnapshotMock(...args),
  },
}));

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

describe("Inspection/fire next actions", () => {
  beforeEach(() => {
    getInspectionWorkspaceSnapshotMock.mockReset();
    getFireTrainingSnapshotMock.mockReset();
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

    render(
      <MemoryRouter>
        <FireTrainingPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/блокеры и дальнейшие действия/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/просроченные записи/i)).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "FireTrainingPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
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
