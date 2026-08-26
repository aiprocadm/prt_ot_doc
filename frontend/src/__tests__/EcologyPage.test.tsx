import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EcologyPage from "@/pages/ecology/EcologyPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const listFacilitiesMock = vi.fn();
const listPassportsMock = vi.fn();
const listMovementsMock = vi.fn();
const listSourcesMock = vi.fn();
const listNormsMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/ecology", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ecologyApi: {
    listFacilities: (...args: unknown[]) => listFacilitiesMock(...args),
    listWastePassports: (...args: unknown[]) => listPassportsMock(...args),
    listWasteMovements: (...args: unknown[]) => listMovementsMock(...args),
    listEmissionSources: (...args: unknown[]) => listSourcesMock(...args),
    listEmissionNorms: (...args: unknown[]) => listNormsMock(...args),
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

/** Паспорта: у одного лимит превышен, у другого лимита нет вовсе. */
const populatedPassports = [
  {
    id: "wp-1",
    name: "Отходы минеральных масел моторных",
    fkko_code: "40611001313",
    hazard_class: "III",
    hazard_class_label: "III класс — умеренно опасные",
    facility_id: null,
    approved_on: "2025-03-01",
    annual_limit_tons: "2.000",
    notes: null,
    generated_this_year_tons: "2.500",
    over_limit: true,
  },
  {
    id: "wp-2",
    name: "Лом чёрных металлов",
    fkko_code: "46101001513",
    hazard_class: "IV",
    hazard_class_label: "IV класс — малоопасные",
    facility_id: null,
    approved_on: null,
    annual_limit_tons: null,
    notes: null,
    generated_this_year_tons: "10.000",
    over_limit: false,
  },
];

/** Журнал учёта: образование и передача оператору по договору. */
const populatedMovements = [
  {
    id: "wm-1",
    passport_id: "wp-1",
    kind: "transferred",
    kind_label: "Передача оператору",
    happened_on: "2026-08-01",
    quantity_tons: "2.000",
    contract_id: "contract-1",
    counterparty: "ООО «Экооператор»",
    notes: null,
  },
  {
    id: "wm-2",
    passport_id: "wp-1",
    kind: "generated",
    kind_label: "Образование",
    happened_on: "2026-07-15",
    quantity_tons: "2.500",
    contract_id: null,
    counterparty: null,
    notes: null,
  },
];

/** Источники выбросов: один с нормативами, один без. */
const populatedSources = [
  {
    id: "es-1",
    facility_id: "nvos-1",
    source_number: "0001",
    name: "Труба котельной",
    kind: "organized",
    kind_label: "Организованный источник",
    location: "Котельная, ось А",
    inventoried_on: "2025-06-01",
    notes: null,
    norms_count: 2,
  },
  {
    id: "es-2",
    facility_id: "nvos-1",
    source_number: "0002",
    name: "Открытый склад сыпучих",
    kind: "unorganized",
    kind_label: "Неорганизованный источник",
    location: null,
    inventoried_on: null,
    notes: null,
    norms_count: 0,
  },
];

/** Нормативы: один действует, у второго разрешение просрочено. */
const populatedNorms = [
  {
    id: "en-1",
    source_id: "es-1",
    substance: "Азота диоксид",
    limit_grams_per_second: "0.025000",
    limit_tons_per_year: "0.780",
    permit_number: "РВ-77-000123",
    valid_until: "2029-01-01",
    notes: null,
    validity_status: "ok",
    validity_status_label: "Действует",
  },
  {
    id: "en-2",
    source_id: "es-1",
    substance: "Углерода оксид",
    limit_grams_per_second: null,
    limit_tons_per_year: "1.200",
    permit_number: null,
    valid_until: "2020-01-01",
    notes: null,
    validity_status: "overdue",
    validity_status_label: "Разрешение просрочено",
  },
];

const populatedReadiness = {
  total_facilities: 2,
  by_category: { I: 0, II: 1, III: 0, IV: 1 },
  excluded_facilities: 1,
  never_actualized: 1,
  waste_passports: 2,
  waste_movements: 2,
  waste_over_limit: 1,
  emission_sources: 2,
  emission_sources_without_norms: 1,
  emission_norms: 2,
  emission_permits_overdue: 1,
};

describe("EcologyPage", () => {
  beforeEach(() => {
    listFacilitiesMock.mockReset();
    listPassportsMock.mockReset();
    listMovementsMock.mockReset();
    listSourcesMock.mockReset();
    listNormsMock.mockReset();
    readinessMock.mockReset();
    listFacilitiesMock.mockResolvedValue(populatedFacilities);
    listPassportsMock.mockResolvedValue(populatedPassports);
    listMovementsMock.mockResolvedValue(populatedMovements);
    listSourcesMock.mockResolvedValue(populatedSources);
    listNormsMock.mockResolvedValue(populatedNorms);
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

  // Доп. №1 разд. 55.2 срез-2: отходы. Паспорт — только I–IV класса; лимит
  // берётся из документа, платформа его не рассчитывает.
  it("паспорта отходов открываются второй секцией", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Производственная площадка №1"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Паспорта отходов" }));

    expect(
      await screen.findByText("Отходы минеральных масел моторных"),
    ).toBeInTheDocument();
    // Класс — словами; превышение лимита названо словом.
    expect(
      screen.getByText("III класс — умеренно опасные"),
    ).toBeInTheDocument();
    expect(screen.getByText(/· превышен$/)).toBeInTheDocument();
    // Отсутствие лимита названо словами, а не пустой ячейкой.
    expect(screen.getByText("не установлен")).toBeInTheDocument();
    // И граница названа на экране.
    expect(
      screen.getByText(/платформа его не рассчитывает/i),
    ).toBeInTheDocument();
  });

  it("журнал учёта отходов открывается третьей секцией", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Производственная площадка №1"),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Журнал учёта отходов" }),
    );

    expect(await screen.findByText("Передача оператору")).toBeInTheDocument();
    expect(screen.getByText("Образование")).toBeInTheDocument();
    expect(screen.getByText("ООО «Экооператор»")).toBeInTheDocument();
    // Движение по договору помечено — договор живёт в ядре, здесь только ссылка.
    expect(screen.getByText("по договору")).toBeInTheDocument();
  });

  // Доп. №1 разд. 55.2 срез-3: выбросы. Инвентаризация источников и нормативы
  // по веществам; ПДВ платформа не рассчитывает.
  it("выбросы открываются четвёртой секцией", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Производственная площадка №1"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Выбросы" }));

    expect(await screen.findByText("Труба котельной")).toBeInTheDocument();
    // Тип источника — словами.
    expect(screen.getByText("Организованный источник")).toBeInTheDocument();
    expect(screen.getByText("Неорганизованный источник")).toBeInTheDocument();
    // Отсутствие инвентаризации и нормативов названо словами.
    expect(screen.getByText("не проводилась")).toBeInTheDocument();
    expect(screen.getByText("нет")).toBeInTheDocument();
    // Нормативы по веществам с состоянием разрешения.
    expect(screen.getByText("Азота диоксид")).toBeInTheDocument();
    expect(screen.getByText("Разрешение просрочено")).toBeInTheDocument();
    // Пустой срок разрешения — «бессрочно», а не «просрочено».
    expect(
      screen.getByText(/платформа их не рассчитывает/i),
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
