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
const listPlanMock = vi.fn();
const listMeasurementsMock = vi.fn();
const listWaterPointsMock = vi.fn();
const listWaterRecordsMock = vi.fn();
const listFeeRatesMock = vi.fn();
const listFeeLinesMock = vi.fn();
const readinessMock = vi.fn();

vi.mock("@/api/ecology", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ecologyApi: {
    listFacilities: (...args: unknown[]) => listFacilitiesMock(...args),
    listWastePassports: (...args: unknown[]) => listPassportsMock(...args),
    listWasteMovements: (...args: unknown[]) => listMovementsMock(...args),
    listEmissionSources: (...args: unknown[]) => listSourcesMock(...args),
    listEmissionNorms: (...args: unknown[]) => listNormsMock(...args),
    listMonitoringPlan: (...args: unknown[]) => listPlanMock(...args),
    listEmissionMeasurements: (...args: unknown[]) =>
      listMeasurementsMock(...args),
    listWaterPoints: (...args: unknown[]) => listWaterPointsMock(...args),
    listWaterRecords: (...args: unknown[]) => listWaterRecordsMock(...args),
    listFeeRates: (...args: unknown[]) => listFeeRatesMock(...args),
    listFeeLines: (...args: unknown[]) => listFeeLinesMock(...args),
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

/** План-график ПЭК: одна строка просрочена, вторая идёт по графику. */
const populatedPlan = [
  {
    id: "mp-1",
    source_id: "es-1",
    substance: "Азота диоксид",
    periodicity_months: 3,
    periodicity_label: "раз в квартал",
    next_due_on: "2026-08-01",
    method: "ПНД Ф 13.1:2:3.25-99",
    laboratory: "ИЛЦ «Эковоздух»",
    notes: null,
    status: "overdue",
    status_label: "Замер просрочен",
    last_measured_on: "2026-05-05",
  },
  {
    id: "mp-2",
    source_id: "es-1",
    substance: "Углерода оксид",
    periodicity_months: 12,
    periodicity_label: "ежегодно",
    next_due_on: "2027-03-01",
    method: null,
    laboratory: null,
    notes: null,
    status: "ok",
    status_label: "По графику",
    last_measured_on: null,
  },
];

/** Замеры: один с превышением, один без внесённого норматива. */
const populatedMeasurements = [
  {
    id: "em-1",
    plan_id: "mp-1",
    source_id: "es-1",
    substance: "Азота диоксид",
    measured_on: "2026-05-05",
    value_grams_per_second: "0.031000",
    protocol_number: "П-2026-014",
    laboratory: "ИЛЦ «Эковоздух»",
    notes: null,
    norm_grams_per_second: "0.025000",
    comparison: "exceeded",
    comparison_label: "Превышение норматива",
  },
  {
    id: "em-2",
    plan_id: null,
    source_id: "es-2",
    substance: "Взвешенные вещества",
    measured_on: "2026-04-01",
    value_grams_per_second: "9.500000",
    protocol_number: null,
    laboratory: null,
    notes: null,
    norm_grams_per_second: null,
    comparison: "no_norm",
    comparison_label: "Норматив не внесён",
  },
];

/** Точки водопользования: забор с превышением лимита и бессрочный сброс. */
const populatedWaterPoints = [
  {
    id: "wp-1",
    facility_id: "nvos-1",
    point_number: "В-1",
    name: "Скважина №1",
    kind: "intake",
    kind_label: "Водозабор",
    water_body: "Подземный водоносный горизонт",
    permit_number: "МОС-00123-ВХ",
    permit_valid_until: "2029-01-01",
    annual_limit_cubic_meters: "500.000",
    notes: null,
    permit_status: "ok",
    permit_status_label: "Действует",
    volume_this_year: "700.000",
    over_limit: true,
  },
  {
    id: "wp-2",
    facility_id: "nvos-1",
    point_number: "С-1",
    name: "Выпуск №1",
    kind: "discharge",
    kind_label: "Сброс сточных вод",
    water_body: null,
    permit_number: null,
    permit_valid_until: null,
    annual_limit_cubic_meters: null,
    notes: null,
    permit_status: "ok",
    permit_status_label: "Действует",
    volume_this_year: "400.000",
    over_limit: false,
  },
];

/** Записи учёта: прибор и расчёт. */
const populatedWaterRecords = [
  {
    id: "wr-1",
    point_id: "wp-1",
    period_year: 2026,
    period_month: 2,
    period_label: "февраль 2026",
    volume_cubic_meters: "700.000",
    basis: "meter",
    basis_label: "Прибор учёта",
    meter_number: "СВК-15 №77123",
    notes: null,
  },
  {
    id: "wr-2",
    point_id: "wp-2",
    period_year: 2026,
    period_month: 1,
    period_label: "январь 2026",
    volume_cubic_meters: "400.000",
    basis: "calculation",
    basis_label: "Расчётный метод",
    meter_number: null,
    notes: null,
  },
];

/** Ставки платы: внесена только одна. */
const populatedFeeRates = [
  {
    id: "fr-1",
    year: 2026,
    impact_kind: "emission",
    impact_kind_label: "Выбросы в атмосферу",
    subject: "Азота диоксид",
    rate_per_ton: "138.80",
    source_document: "Постановление Правительства РФ",
    notes: null,
  },
];

/** Строки расчёта: одна посчитана, вторая без ставки. */
const populatedFeeLines = [
  {
    id: "fl-1",
    year: 2026,
    quarter: 1,
    impact_kind: "emission",
    impact_kind_label: "Выбросы в атмосферу",
    subject: "Азота диоксид",
    mass_tons: "2.000",
    coefficient: "1.00",
    notes: null,
    rate_status: "found",
    rate_status_label: "Ставка внесена",
    rate_per_ton: "138.80",
    amount_rubles: "277.60",
  },
  {
    id: "fl-2",
    year: 2026,
    quarter: 2,
    impact_kind: "waste",
    impact_kind_label: "Размещение отходов",
    subject: "Отходы IV класса опасности",
    mass_tons: "5.000",
    coefficient: "1.00",
    notes: null,
    rate_status: "missing",
    rate_status_label: "Ставка не внесена",
    rate_per_ton: null,
    amount_rubles: null,
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
  monitoring_plan_items: 2,
  monitoring_overdue: 1,
  measurements_this_year: 2,
  measurements_exceeded: 1,
  water_points: 2,
  water_permits_overdue: 0,
  water_intake_cubic_meters: "700.000",
  water_discharge_cubic_meters: "400.000",
  water_over_limit: 1,
  fee_lines: 2,
  fee_lines_without_rate: 1,
  fee_total_rubles: "277.60",
};

describe("EcologyPage", () => {
  beforeEach(() => {
    listFacilitiesMock.mockReset();
    listPassportsMock.mockReset();
    listMovementsMock.mockReset();
    listSourcesMock.mockReset();
    listNormsMock.mockReset();
    listPlanMock.mockReset();
    listMeasurementsMock.mockReset();
    listWaterPointsMock.mockReset();
    listWaterRecordsMock.mockReset();
    listFeeRatesMock.mockReset();
    listFeeLinesMock.mockReset();
    readinessMock.mockReset();
    listFacilitiesMock.mockResolvedValue(populatedFacilities);
    listPassportsMock.mockResolvedValue(populatedPassports);
    listMovementsMock.mockResolvedValue(populatedMovements);
    listSourcesMock.mockResolvedValue(populatedSources);
    listNormsMock.mockResolvedValue(populatedNorms);
    listPlanMock.mockResolvedValue(populatedPlan);
    listMeasurementsMock.mockResolvedValue(populatedMeasurements);
    listWaterPointsMock.mockResolvedValue(populatedWaterPoints);
    listWaterRecordsMock.mockResolvedValue(populatedWaterRecords);
    listFeeRatesMock.mockResolvedValue(populatedFeeRates);
    listFeeLinesMock.mockResolvedValue(populatedFeeLines);
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

  // Доп. №1 разд. 55.2 срез-4: ПЭК. График замеров и сами замеры; превышение
  // здесь — сравнение замера с внесённым нормативом, а не суждение платформы.
  it("ПЭК открывается пятой секцией", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Производственная площадка №1"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "ПЭК и замеры" }));

    // Периодичность — словами, а не числом месяцев.
    expect(await screen.findByText("раз в квартал")).toBeInTheDocument();
    expect(screen.getByText("ежегодно")).toBeInTheDocument();
    // Состояние строки графика названо словами.
    expect(screen.getByText("Замер просрочен")).toBeInTheDocument();
    expect(screen.getByText("По графику")).toBeInTheDocument();
    // Пустая клетка запрещена: «замеров не было» вместо прочерка.
    expect(screen.getByText("замеров не было")).toBeInTheDocument();
    // Итог сравнения — и превышение, и честное «норматива нет».
    expect(screen.getByText("Превышение норматива")).toBeInTheDocument();
    expect(screen.getByText("Норматив не внесён")).toBeInTheDocument();
    // Граница названа на экране.
    expect(screen.getByText(/платформа её не назначает/i)).toBeInTheDocument();
  });

  // Доп. №1 разд. 55.2 срез-5: водопользование. Забор и сброс — разные
  // величины, поэтому в сводке они стоят раздельно.
  it("водопользование открывается шестой секцией", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Производственная площадка №1"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Водопользование" }));

    expect(await screen.findByText("Скважина №1")).toBeInTheDocument();
    // Тип точки — словами.
    expect(screen.getByText("Водозабор")).toBeInTheDocument();
    expect(screen.getByText("Сброс сточных вод")).toBeInTheDocument();
    // Пустые клетки запрещены: «не указан» и «бессрочно» вместо прочерка.
    expect(screen.getByText("не указан")).toBeInTheDocument();
    expect(screen.getByText("бессрочно")).toBeInTheDocument();
    // Превышение лимита названо прямо в клетке объёма.
    expect(screen.getByText("700.000 — превышен лимит")).toBeInTheDocument();
    // Учёт: период словами и основание из закрытого словаря.
    expect(screen.getByText("февраль 2026")).toBeInTheDocument();
    expect(screen.getByText("Расчётный метод")).toBeInTheDocument();
    // Забор и сброс показаны раздельно, а не одной суммой.
    expect(screen.getByText(/Забор за год: 700.000/)).toBeInTheDocument();
  });

  // Доп. №1 разд. 55.3 срез-6: плата за НВОС. Без ставки сумма не считается
  // вовсе — в клетке стоит причина, а не ноль.
  it("плата за НВОС открывается седьмой секцией", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <EcologyPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Производственная площадка №1"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Плата за НВОС" }));

    // Посчитанная строка показывает сумму.
    expect(await screen.findByText("277.60")).toBeInTheDocument();
    // Строка без ставки показывает ПРИЧИНУ, а не ноль.
    expect(screen.getByText("Ставка не внесена")).toBeInTheDocument();
    // Вид воздействия — словами.
    expect(screen.getAllByText("Выбросы в атмосферу").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText("Размещение отходов")).toBeInTheDocument();
    // Граница названа на экране.
    expect(
      screen.getByText(/сумма не считается вовсе — это не ноль/i),
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
