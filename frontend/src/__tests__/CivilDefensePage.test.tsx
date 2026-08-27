import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CivilDefensePage from "@/pages/civilDefense/CivilDefensePage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listFormationsMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/civilDefense", () => ({
  civilDefenseApi: {
    listFormations: (...args: unknown[]) => listFormationsMock(...args),
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

const populatedReadiness = {
  total_formations: 2,
  by_kind: { nasf: 1, nfgo: 1 },
  without_commander: 1,
  members_active: 3,
};

describe("CivilDefensePage", () => {
  beforeEach(() => {
    listFormationsMock.mockReset();
    readinessMock.mockReset();
    listFormationsMock.mockResolvedValue(populatedFormations);
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
    readinessMock.mockResolvedValue({
      total_formations: 0,
      by_kind: { nasf: 0, nfgo: 0 },
      without_commander: 0,
      members_active: 0,
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
