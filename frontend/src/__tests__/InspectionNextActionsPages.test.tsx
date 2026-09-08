import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";

import FireInspectionsPage from "@/pages/fire-inspections/FireInspectionsPage";
import FireTrainingPage from "@/pages/fire-training/FireTrainingPage";
import InspectionPrepPackagesPage from "@/pages/inspection-prep/InspectionPrepPackagesPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getInspectionWorkspaceSnapshotMock = vi.fn();
const getFireTrainingSnapshotMock = vi.fn();
const listDrillsMock = vi.fn();
const readinessMock = vi.fn();
const createDrillMock = vi.fn();
const updateDrillMock = vi.fn();
const listSitesMock = vi.fn();

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getInspectionWorkspaceSnapshot: (...args: unknown[]) =>
      getInspectionWorkspaceSnapshotMock(...args),
    getFireTrainingSnapshot: (...args: unknown[]) =>
      getFireTrainingSnapshotMock(...args),
  },
}));

vi.mock("@/api/fireSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  fireSafetyApi: {
    listDrills: (...args: unknown[]) => listDrillsMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
    createDrill: (...args: unknown[]) => createDrillMock(...args),
    updateDrill: (...args: unknown[]) => updateDrillMock(...args),
  },
}));

vi.mock("@/api/sites", () => ({
  sitesApi: { list: (...args: unknown[]) => listSitesMock(...args) },
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

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
    // Срез-120: кнопки записи закрыты правом `<контур>.manage` — экран
    // рендерится от лица того, кому запись разрешена.
    useAuthStore.setState({
      user: {
        id: "discipline-writer",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "writer@example.com",
        full_name: "Discipline Writer",
        roles: ["ot_specialist"],
        permissions: [
          PERMISSIONS.FIRE_SAFETY_VIEW,
          PERMISSIONS.FIRE_SAFETY_MANAGE,
        ],
        attributes: { tenant_id: "tenant-1" },
      },
      loading: false,
      error: null,
    } as never);
    getInspectionWorkspaceSnapshotMock.mockReset();
    getFireTrainingSnapshotMock.mockReset();
    listDrillsMock.mockReset();
    readinessMock.mockReset();
    createDrillMock.mockReset();
    updateDrillMock.mockReset();
    listSitesMock.mockReset();
    listDrillsMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue(emptyReadiness);
    listSitesMock.mockResolvedValue({
      items: [{ id: "site-1", name: "Площадка №1" }],
      total: 1,
    });
  });

  it("тренировка планируется с экрана, а не только через API (срез-104)", async () => {
    const user = userEvent.setup();
    getFireTrainingSnapshotMock.mockResolvedValue({
      templates: [],
      journals: [],
      overdueEntries: [],
      programs: [],
    });
    const added = {
      ...populatedDrill,
      id: "drill-new",
      title: "Учение с пожарной охраной",
    };
    createDrillMock.mockResolvedValue(added);
    listDrillsMock
      .mockResolvedValueOnce([populatedDrill])
      .mockResolvedValue([populatedDrill, added]);

    render(
      <MemoryRouter>
        <FireTrainingPage />
      </MemoryRouter>,
    );
    await screen.findByText("Тренировка по эвакуации, корпус А");

    await user.click(
      screen.getByRole("button", { name: "Запланировать тренировку" }),
    );
    await user.selectOptions(screen.getByLabelText("Вид"), "joint");
    await user.type(
      screen.getByLabelText("Тренировка"),
      "Учение с пожарной охраной",
    );
    await user.type(screen.getByLabelText("По плану"), "2026-11-10");
    await user.selectOptions(screen.getByLabelText("Площадка"), "site-1");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(createDrillMock).toHaveBeenCalled());
    expect(createDrillMock.mock.calls[0][0]).toMatchObject({
      kind: "joint",
      title: "Учение с пожарной охраной",
      planned_on: "2026-11-10",
      site_id: "site-1",
      // Протокола ещё нет: дата проведения и результат пусты.
      held_on: null,
      outcome: null,
      participants: null,
    });
    expect(
      await screen.findByText("Учение с пожарной охраной"),
    ).toBeInTheDocument();
  });

  it("протокол вносится из строки непроведённой тренировки (срез-104)", async () => {
    const user = userEvent.setup();
    getFireTrainingSnapshotMock.mockResolvedValue({
      templates: [],
      journals: [],
      overdueEntries: [],
      programs: [],
    });
    listDrillsMock.mockResolvedValue([populatedDrill]);
    updateDrillMock.mockResolvedValue({
      ...populatedDrill,
      held_on: "2026-08-05",
      outcome: "with_remarks",
    });

    render(
      <MemoryRouter>
        <FireTrainingPage />
      </MemoryRouter>,
    );
    await screen.findByText("Тренировка по эвакуации, корпус А");

    // У непроведённой тренировки кнопка называется «Протокол», а не «Изменить».
    await user.click(screen.getByRole("button", { name: "Протокол" }));
    await user.click(
      screen.getByText(
        "Протокол проведения: дата, результат, участники, анализ",
      ),
    );
    await user.type(screen.getByLabelText("Проведена"), "2026-08-05");
    await user.selectOptions(
      screen.getByLabelText("Результат"),
      "with_remarks",
    );
    await user.type(screen.getByLabelText("Участников"), "42");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(updateDrillMock).toHaveBeenCalled());
    expect(updateDrillMock.mock.calls[0][0]).toBe("drill-1");
    expect(updateDrillMock.mock.calls[0][1]).toMatchObject({
      held_on: "2026-08-05",
      outcome: "with_remarks",
      participants: 42,
      planned_on: "2026-08-01",
    });
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
