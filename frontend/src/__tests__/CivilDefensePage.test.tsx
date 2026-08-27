import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CivilDefensePage from "@/pages/civilDefense/CivilDefensePage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listFormationsMock = vi.fn();
const listDrillsMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/civilDefense", () => ({
  civilDefenseApi: {
    listFormations: (...args: unknown[]) => listFormationsMock(...args),
    listDrills: (...args: unknown[]) => listDrillsMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

/** Доп. №1 разд. 56.1 срез-1: формирования с командиром и без. */
const populatedFormations = [
  {
    id: "cd-1",
    name: "Звено пожаротушения",
    kind: "nasf",
    kind_label: "НАСФ (аварийно-спасательное формирование)",
    purpose: "Тушение возгораний до прибытия подразделений",
    commander_person_id: "p-1",
    commander_name: "Командиров Пётр Иванович",
    equipment_notes: null,
    notes: null,
    members_active: 3,
  },
  {
    id: "cd-2",
    name: "Эвакуационная группа",
    kind: "nfgo",
    kind_label: "НФГО (формирование по обеспечению ГО)",
    purpose: null,
    commander_person_id: null,
    commander_name: null,
    equipment_notes: null,
    notes: null,
    members_active: 0,
  },
];

/** Учения: просроченное общеобъектовое и проведённое силами звена. */
const populatedDrills = [
  {
    id: "d-1",
    kind: "facility_training",
    kind_label: "Объектовая тренировка",
    title: "Тренировка по сигналу «Внимание всем»",
    planned_on: "2026-08-01",
    held_on: null,
    formation_id: null,
    formation_name: null,
    site_id: null,
    scenario: null,
    participants: null,
    outcome: null,
    outcome_label: null,
    findings: null,
    status: "overdue",
    status_label: "Просрочено",
  },
  {
    id: "d-2",
    kind: "command_staff",
    kind_label: "Командно-штабное учение",
    title: "КШУ по ликвидации ЧС",
    planned_on: "2026-06-10",
    held_on: "2026-06-10",
    formation_id: "cd-1",
    formation_name: "Звено пожаротушения",
    site_id: null,
    scenario: null,
    participants: 24,
    outcome: "with_remarks",
    outcome_label: "Проведено с замечаниями",
    findings: null,
    status: "held",
    status_label: "Проведено",
  },
];

const populatedReadiness = {
  total_formations: 2,
  by_kind: { nasf: 1, nfgo: 1 },
  without_commander: 1,
  members_active: 3,
  drills_total: 2,
  drills_overdue: 1,
  drills_held_this_year: 1,
};

describe("CivilDefensePage", () => {
  beforeEach(() => {
    listFormationsMock.mockReset();
    listDrillsMock.mockReset();
    readinessMock.mockReset();
    listFormationsMock.mockResolvedValue(populatedFormations);
    listDrillsMock.mockResolvedValue(populatedDrills);
    readinessMock.mockResolvedValue(populatedReadiness);
  });

  it("рендерит реестр формирований с видами словами", async () => {
    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Звено пожаротушения")).toBeInTheDocument();
    // Вид — словами из закрытого словаря, а не кодом.
    expect(
      screen.getByText("НАСФ (аварийно-спасательное формирование)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("НФГО (формирование по обеспечению ГО)"),
    ).toBeInTheDocument();
    // Пустые клетки запрещены: состояние названо словами.
    expect(screen.getByText("не назначен")).toBeInTheDocument();
    expect(screen.getByText("состав не внесён")).toBeInTheDocument();
    // Граница названа на экране: платформа не выносит вердиктов.
    expect(screen.getByText(/не выносит вердиктов/i)).toBeInTheDocument();
  });

  it("пустой реестр объясняет, что вносить", async () => {
    listFormationsMock.mockResolvedValue([]);
    listDrillsMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      total_formations: 0,
      by_kind: { nasf: 0, nfgo: 0 },
      without_commander: 0,
      members_active: 0,
      drills_total: 0,
      drills_overdue: 0,
      drills_held_this_year: 0,
    });

    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Формирования не заведены"),
    ).toBeInTheDocument();
  });

  // Доп. №1 разд. 56.1 срез-2: учения. «Журнал» — реестр с фактическими
  // датами; периодичность платформа не назначает.
  it("учения открываются второй секцией", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Звено пожаротушения")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Учения и тренировки" }),
    );

    expect(await screen.findByText("КШУ по ликвидации ЧС")).toBeInTheDocument();
    // Вид и состояние — словами из закрытых словарей.
    expect(screen.getByText("Командно-штабное учение")).toBeInTheDocument();
    expect(screen.getByText("Просрочено")).toBeInTheDocument();
    // Пустые клетки запрещены: причина названа словами.
    expect(screen.getByText("не проводилось")).toBeInTheDocument();
    // Учение без формирования — это весь персонал, а не прочерк.
    expect(screen.getByText("весь персонал")).toBeInTheDocument();
    // Граница названа на экране.
    expect(screen.getByText(/сроки не назначает/i)).toBeInTheDocument();
  });

  it("CivilDefensePage в UX-бюджете", async () => {
    render(
      <MemoryRouter>
        <CivilDefensePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Звено пожаротушения")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "CivilDefensePage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
