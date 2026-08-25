import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EcologyPage from "@/pages/ecology/EcologyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listFacilitiesMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/ecology", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ecologyApi: {
    listFacilities: (...args: unknown[]) => listFacilitiesMock(...args),
    readiness: (...args: unknown[]) => readinessMock(...args),
  },
}));

/** Объекты НВОС: один со свежими сведениями, другой без актуализации. */
const populatedFacilities = [
  {
    id: "nvos-1",
    name: "Производственная площадка №1",
    register_number: "12-0177-001234-П",
    category: "II",
    category_label: "II категория — умеренное негативное воздействие",
    site_id: "site-1",
    registered_on: "2019-04-10",
    actualized_on: "2026-02-01",
    excluded_on: null,
    status: "registered",
    status_label: "На государственном учёте",
    responsible: "Эколог Иванова",
    notes: null,
  },
  {
    id: "nvos-2",
    name: "Склад ГСМ",
    register_number: "12-0177-004321-П",
    category: "IV",
    category_label: "IV категория — минимальное негативное воздействие",
    site_id: null,
    registered_on: null,
    actualized_on: null,
    excluded_on: null,
    status: "registered",
    status_label: "На государственном учёте",
    responsible: null,
    notes: null,
  },
];

const populatedReadiness = {
  total_facilities: 2,
  by_category: { I: 0, II: 1, III: 0, IV: 1 },
  excluded_facilities: 1,
  never_actualized: 1,
};

describe("EcologyPage", () => {
  beforeEach(() => {
    listFacilitiesMock.mockReset();
    readinessMock.mockReset();
    listFacilitiesMock.mockResolvedValue(populatedFacilities);
    readinessMock.mockResolvedValue(populatedReadiness);
  });

  it("рисует реестр объектов НВОС с категорией словами", async () => {
    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Производственная площадка №1"),
    ).toBeInTheDocument();
    // Категория — словами, а не кодом «II».
    expect(
      screen.getByText("II категория — умеренное негативное воздействие"),
    ).toBeInTheDocument();
    expect(screen.getByText("12-0177-001234-П")).toBeInTheDocument();
    // Отсутствие актуализации названо словами, а не пустой ячейкой.
    expect(screen.getByText("не актуализировались")).toBeInTheDocument();
  });

  it("разрез по категориям виден в шапке", async () => {
    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    // От категории зависят режим надзора и состав отчётности.
    expect(await screen.findByText("I категория")).toBeInTheDocument();
    expect(screen.getByText("IV категория")).toBeInTheDocument();
    expect(screen.getByText(/объектов на учёте/i)).toBeInTheDocument();
    expect(screen.getByText(/без актуализации сведений/i)).toBeInTheDocument();
  });

  it("экран не выдаёт категорию за своё вычисление", async () => {
    // ГРАНИЦА названа НА ЭКРАНЕ: категорию присваивают при постановке на
    // государственный учёт, исходных данных для вывода в системе нет.
    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/платформа её не вычисляет/i),
    ).toBeInTheDocument();
  });

  it("пустой реестр объясняет, что вносить", async () => {
    listFacilitiesMock.mockResolvedValue([]);
    readinessMock.mockResolvedValue({
      total_facilities: 0,
      by_category: { I: 0, II: 0, III: 0, IV: 0 },
      excluded_facilities: 0,
      never_actualized: 0,
    });

    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/объекты НВОС не заведены/i),
    ).toBeInTheDocument();
    // Подсказка называет источник сведений — свидетельство о постановке на
    // учёт (текст про границу категории на экране тоже есть, поэтому матчим
    // то, что встречается только в подсказке пустого реестра).
    expect(
      screen.getByText(/код объекта в реестре и категорию/i),
    ).toBeInTheDocument();
  });

  it("EcologyPage в UX-бюджете", async () => {
    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Производственная площадка №1"),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "EcologyPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
