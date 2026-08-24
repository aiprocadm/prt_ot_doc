import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IndustrialSafetyPage from "@/pages/industrial-safety/IndustrialSafetyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listFacilitiesMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/industrialSafety", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  industrialSafetyApi: {
    listFacilities: (...args: unknown[]) => listFacilitiesMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

/** Два ОПО на одной площадке — то, чего полями площадки не выразить. */
const populatedFacilities = [
  {
    id: "opo-1",
    name: "Сеть газопотребления котельной",
    register_number: "А01-12345-0001",
    hazard_class: "III",
    hazard_class_label: "III класс — средняя опасность",
    site_id: "site-1",
    registered_on: "2021-06-15",
    excluded_on: null,
    status: "registered",
    status_label: "Зарегистрирован",
    responsible: "Главный инженер Петров",
    notes: null,
  },
  {
    id: "opo-2",
    name: "Площадка кранов",
    register_number: "А01-12345-0002",
    hazard_class: "IV",
    hazard_class_label: "IV класс — низкая опасность",
    site_id: "site-1",
    registered_on: null,
    excluded_on: null,
    status: "registered",
    status_label: "Зарегистрирован",
    responsible: null,
    notes: null,
  },
];

const populatedReadiness = {
  total_facilities: 2,
  by_class: { I: 0, II: 0, III: 1, IV: 1 },
  excluded_facilities: 1,
};

describe("IndustrialSafetyPage", () => {
  beforeEach(() => {
    listFacilitiesMock.mockReset();
    readinessMock.mockReset();
    listFacilitiesMock.mockResolvedValue(populatedFacilities);
    readinessMock.mockResolvedValue(populatedReadiness);
  });

  it("рисует реестр ОПО с классом словами", async () => {
    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Сеть газопотребления котельной"),
    ).toBeInTheDocument();
    // Класс — словами, а не кодом «III»: код человеку ничего не говорит.
    expect(
      screen.getByText("III класс — средняя опасность"),
    ).toBeInTheDocument();
    expect(screen.getByText("А01-12345-0001")).toBeInTheDocument();
    // Два объекта на ОДНОЙ площадке — ради этого реестр и заводился.
    expect(screen.getByText("Площадка кранов")).toBeInTheDocument();
  });

  it("разрез по классам виден в шапке", async () => {
    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    // От класса зависит режим надзора: I и II — постоянный госнадзор.
    expect(await screen.findByText("I класс")).toBeInTheDocument();
    expect(screen.getByText("II класс")).toBeInTheDocument();
    expect(screen.getByText(/действующих ОПО/i)).toBeInTheDocument();
    expect(screen.getByText(/исключено из реестра/i)).toBeInTheDocument();
  });

  it("пустой реестр объясняет, что вносить", async () => {
    listFacilitiesMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      total_facilities: 0,
      by_class: { I: 0, II: 0, III: 0, IV: 0 },
      excluded_facilities: 0,
    });

    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/объекты не заведены/i)).toBeInTheDocument();
    // Подсказка называет и источник сведений, и то, что объектов бывает много.
    expect(
      screen.getByText(/свидетельства о регистрации/i),
    ).toBeInTheDocument();
  });

  it("IndustrialSafetyPage в UX-бюджете", async () => {
    render(
      <MemoryRouter>
        <IndustrialSafetyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Сеть газопотребления котельной"),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "IndustrialSafetyPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
