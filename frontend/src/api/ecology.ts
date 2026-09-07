import { apiClient } from "@/api/client";

/**
 * Контур экологии (Доп. №1 разд. 55.1): объекты негативного воздействия на
 * окружающую среду (НВОС).
 *
 * Ручки гейтятся модулем `ecology`: у арендатора без выдачи — 404, у
 * выдававшегося-отключённого чтение остаётся (read-only, BIZ-61).
 */

export type NvosCategory = "I" | "II" | "III" | "IV";

/** Подписи категорий — запас; готовую подпись отдаёт сервер. */
export const NVOS_CATEGORY_TITLES: Record<string, string> = {
  I: "I категория — значительное негативное воздействие",
  II: "II категория — умеренное негативное воздействие",
  III: "III категория — незначительное негативное воздействие",
  IV: "IV категория — минимальное негативное воздействие",
};

/**
 * Состояние объекта в государственном реестре — копия `NVOS_STATUSES`
 * бэкенда. Форма строит выбор из этого map; совпадение стережёт
 * `tests/test_ecology_nvos.py` (срез-99).
 */
export const NVOS_STATUS_TITLES: Record<string, string> = {
  registered: "На государственном учёте",
  excluded: "Снят с учёта",
};

export type EnvironmentalFacilityDto = {
  id: string;
  name: string;
  register_number: string;
  category: string;
  category_label: string;
  site_id?: string | null;
  registered_on?: string | null;
  actualized_on?: string | null;
  excluded_on?: string | null;
  status: string;
  status_label: string;
  responsible?: string | null;
  notes?: string | null;
};

export type EcologyReadinessDto = {
  total_facilities: number;
  /** Категория → число объектов НА УЧЁТЕ; ключи всегда все четыре. */
  by_category: Record<string, number>;
  excluded_facilities: number;
  /**
   * Объекты без единой актуализации сведений — ФАКТ, а не нарушение:
   * обязанность актуализировать возникает при изменении характеристик
   * объекта, а не по календарю.
   */
  never_actualized: number;
  /** Разд. 55.2 «отходы»: паспорта, записи журнала и превышения лимита. */
  waste_passports: number;
  waste_movements: number;
  waste_over_limit: number;
  /**
   * Разд. 55.2 «выбросы»: инвентаризация и нормативы. Полей «предлагаемый
   * норматив» и «превышение» здесь НЕТ — ПДВ устанавливается проектом
   * нормативов, а факт выброса меряется замерами ПЭК.
   */
  emission_sources: number;
  emission_sources_without_norms: number;
  emission_norms: number;
  emission_permits_overdue: number;
  /**
   * Разд. 55.2 «ПЭК»: график замеров, просрочки и превышения ПО ЗАМЕРАМ.
   * Превышение здесь — сравнение двух внесённых чисел (замер и норматив), а
   * не вывод платформы о самом нормативе.
   */
  monitoring_plan_items: number;
  monitoring_overdue: number;
  measurements_this_year: number;
  measurements_exceeded: number;
  /**
   * Разд. 55.2 «водопользование». Забор и сброс считаются РАЗДЕЛЬНО: это
   * разные величины, и складывать их в одну цифру нельзя.
   */
  water_points: number;
  water_permits_overdue: number;
  water_intake_cubic_meters: string;
  water_discharge_cubic_meters: string;
  water_over_limit: number;
  /**
   * Разд. 55.3 «плата за НВОС» за текущий год. Строка без ставки НЕ прибавляет
   * ноль к итогу — иначе итог выглядел бы полным.
   */
  fee_lines: number;
  fee_lines_without_rate: number;
  fee_total_rubles: string;
  /** Доп. №1 разд. 57.4: открытые происшествия этой дисциплины (срез-49). */
  incidents_open: number;
  /**
   * Разд. 55.3 «2-ТП, декларация, платежи» (срез-71): сроки отчётности и
   * платежей, у которых дата прошла, а исполнение не отмечено. Даты вносит
   * эколог — платформа их не назначает и не вычисляет.
   */
  reporting_overdue: number;
};

/**
 * Виды воздействия для платы за НВОС — копия `FEE_IMPACT_KINDS` бэкенда.
 * Формы ставки и строки расчёта строят выбор из этого map; совпадение
 * стережёт `tests/test_ecology_fee.py` (срез-102).
 */
export const FEE_IMPACT_KIND_TITLES: Record<string, string> = {
  emission: "Выбросы в атмосферу",
  discharge: "Сбросы в водные объекты",
  waste: "Размещение отходов",
};

/** Тело ставки платы: год, вид воздействия и предмет — ключ ставки. */
export type FeeRateCreateInput = {
  year: number;
  impact_kind: string;
  subject: string;
  rate_per_ton: string;
  source_document?: string | null;
  notes?: string | null;
};

/** Правка ставки: год, вид и предмет не меняются — это уже другая ставка. */
export type FeeRateUpdateInput = {
  rate_per_ton: string;
  source_document?: string | null;
  notes?: string | null;
};

/** Тело строки расчёта платы: квартал — он же авансовый платёж. */
export type FeeLineCreateInput = {
  year: number;
  quarter: number;
  impact_kind: string;
  subject: string;
  mass_tons: string;
  coefficient: string;
  notes?: string | null;
};

/** Правка строки: год, квартал, вид и предмет не меняются — это ключ строки. */
export type FeeLineUpdateInput = {
  mass_tons: string;
  coefficient: string;
  notes?: string | null;
};

export type FeeRateDto = {
  id: string;
  year: number;
  impact_kind: string;
  impact_kind_label: string;
  subject: string;
  rate_per_ton: string;
  source_document?: string | null;
  notes?: string | null;
};

export type FeeLineDto = {
  id: string;
  year: number;
  quarter: number;
  impact_kind: string;
  impact_kind_label: string;
  subject: string;
  mass_tons: string;
  coefficient: string;
  notes?: string | null;
  /** found | missing — ставка ищется по ГОДУ строки. */
  rate_status: string;
  rate_status_label: string;
  rate_per_ton?: string | null;
  /** null, а НЕ ноль, когда ставка не внесена. */
  amount_rubles?: string | null;
};

/** Тело заведения объекта НВОС: сведения из свидетельства об учёте. */
export type EnvironmentalFacilityCreateInput = {
  name: string;
  register_number: string;
  category: string;
  site_id?: string | null;
  registered_on?: string | null;
  actualized_on?: string | null;
  excluded_on?: string | null;
  status?: string;
  responsible?: string | null;
  notes?: string | null;
};

export type EnvironmentalFacilityUpdateInput = EnvironmentalFacilityCreateInput;

/** Тело паспорта отхода: лимит — из НООЛР или декларации, не расчёт. */
export type WastePassportCreateInput = {
  name: string;
  fkko_code: string;
  hazard_class: string;
  facility_id?: string | null;
  approved_on?: string | null;
  annual_limit_tons?: string | null;
  notes?: string | null;
};

export type WastePassportUpdateInput = WastePassportCreateInput;

/** Срок экологической отчётности или платежа (разд. 55.3, срез-71). */
export type ReportingDeadlineDto = {
  id: string;
  /** report | payment. */
  kind: string;
  kind_label: string;
  title: string;
  period?: string | null;
  /** Дата, внесённая экологом по нормативному акту. */
  due_on: string;
  /** Дата исполнения; пока пусто — срок живёт в календаре и Центре внимания. */
  done_on?: string | null;
  responsible?: string | null;
  notes?: string | null;
  /** planned | overdue | done — выводится на сервере из двух дат. */
  status: string;
  status_label: string;
};

/**
 * Виды срока — копия `REPORTING_KINDS` бэкенда (`models/ecology.py`).
 * Форма строит выпадающий список из этого map, поэтому вид, которого здесь
 * нет, нельзя ни выбрать, ни прочитать словами. Совпадение с бэкендом стережёт
 * `tests/test_ecology_reporting.py` (срез-98).
 */
export const REPORTING_KIND_TITLES: Record<string, string> = {
  report: "Отчётность",
  payment: "Платёж",
};

/** Тело создания срока: дату и вид вносит эколог, состояние не передаётся. */
export type ReportingDeadlineCreateInput = {
  kind: string;
  title: string;
  period?: string | null;
  due_on: string;
  done_on?: string | null;
  responsible?: string | null;
  notes?: string | null;
};

/** Правка срока; `done_on: null` снимает отметку об исполнении. */
export type ReportingDeadlineUpdateInput = Omit<
  ReportingDeadlineCreateInput,
  "kind"
>;

export type WaterPointDto = {
  id: string;
  facility_id: string;
  point_number: string;
  name: string;
  kind: string;
  kind_label: string;
  water_body?: string | null;
  permit_number?: string | null;
  permit_valid_until?: string | null;
  annual_limit_cubic_meters?: string | null;
  notes?: string | null;
  /** ok | due_soon | overdue — пустой срок означает «бессрочно». */
  permit_status: string;
  permit_status_label: string;
  volume_this_year: string;
  /** ФАКТ по внесённому лимиту: без лимита превышения не бывает. */
  over_limit: boolean;
};

export type WaterRecordDto = {
  id: string;
  point_id: string;
  period_year: number;
  period_month: number;
  /** «март 2026» — месяц числом читается хуже, чем словом. */
  period_label: string;
  volume_cubic_meters: string;
  basis: string;
  basis_label: string;
  meter_number?: string | null;
  notes?: string | null;
};

export type MonitoringPlanItemDto = {
  id: string;
  source_id: string;
  substance: string;
  periodicity_months: number;
  /** «раз в квартал» и подобное; нетиповой срок — «раз в N месяцев». */
  periodicity_label: string;
  next_due_on: string;
  method?: string | null;
  laboratory?: string | null;
  notes?: string | null;
  /** ok | due_soon | overdue — считается при чтении по плановой дате. */
  status: string;
  status_label: string;
  last_measured_on?: string | null;
};

export type EmissionMeasurementDto = {
  id: string;
  plan_id?: string | null;
  source_id: string;
  substance: string;
  measured_on: string;
  value_grams_per_second: string;
  protocol_number?: string | null;
  laboratory?: string | null;
  notes?: string | null;
  norm_grams_per_second?: string | null;
  /** within | exceeded | no_norm | no_single_limit */
  comparison: string;
  comparison_label: string;
};

export type EmissionSourceDto = {
  id: string;
  facility_id: string;
  source_number: string;
  name: string;
  kind: string;
  kind_label: string;
  location?: string | null;
  inventoried_on?: string | null;
  notes?: string | null;
  norms_count: number;
};

export type EmissionNormDto = {
  id: string;
  source_id: string;
  substance: string;
  limit_grams_per_second?: string | null;
  limit_tons_per_year?: string | null;
  permit_number?: string | null;
  valid_until?: string | null;
  notes?: string | null;
  /** ok | due_soon | overdue — пустой срок означает «бессрочно». */
  validity_status: string;
  validity_status_label: string;
};

/** Подписи классов отходов — запас; готовую подпись отдаёт сервер. */
export const WASTE_HAZARD_CLASS_TITLES: Record<string, string> = {
  I: "I класс — чрезвычайно опасные",
  II: "II класс — высокоопасные",
  III: "III класс — умеренно опасные",
  IV: "IV класс — малоопасные",
};

export type WastePassportDto = {
  id: string;
  name: string;
  fkko_code: string;
  hazard_class: string;
  hazard_class_label: string;
  facility_id?: string | null;
  approved_on?: string | null;
  /** Годовой лимит из НООЛР/декларации — платформа его не рассчитывает. */
  annual_limit_tons?: string | null;
  notes?: string | null;
  generated_this_year_tons: string;
  over_limit: boolean;
};

/**
 * Виды движения отходов — копия `WASTE_MOVEMENT_KINDS` бэкенда. Свободная
 * строка сделала бы учёт непересчитываемым, а 2-ТП невозможной; форма строит
 * выбор из этого map, совпадение стережёт `tests/test_ecology_waste.py`.
 */
export const WASTE_MOVEMENT_KIND_TITLES: Record<string, string> = {
  generated: "Образование",
  accumulated: "Накопление",
  transferred: "Передача оператору",
  disposed: "Размещение (захоронение)",
  neutralized: "Обезвреживание",
  utilized: "Утилизация",
};

/** Виды источников выбросов — копия `EMISSION_SOURCE_KINDS` бэкенда. */
export const EMISSION_SOURCE_KIND_TITLES: Record<string, string> = {
  organized: "Организованный источник",
  unorganized: "Неорганизованный источник",
};

/**
 * Типовые периодичности замеров ПЭК — копия `PERIODICITY_LABELS` бэкенда
 * (ключ — месяцы). Нетиповой срок сервер подписывает «раз в N месяцев»,
 * поэтому форма разрешает и его.
 */
export const MONITORING_PERIODICITY_TITLES: Record<string, string> = {
  "1": "ежемесячно",
  "3": "раз в квартал",
  "6": "раз в полугодие",
  "12": "ежегодно",
};

/** Виды точек водопользования — копия `WATER_POINT_KINDS` бэкенда. */
export const WATER_POINT_KIND_TITLES: Record<string, string> = {
  intake: "Водозабор",
  discharge: "Сброс сточных вод",
};

/** Чем измерен объём — копия `WATER_RECORD_BASES` бэкенда. */
export const WATER_RECORD_BASIS_TITLES: Record<string, string> = {
  meter: "Прибор учёта",
  calculation: "Расчётный метод",
};

/** Месяцы периода учёта — копия `MONTH_TITLES` бэкенда (ключ — номер). */
export const MONTH_TITLES: Record<string, string> = {
  "1": "январь",
  "2": "февраль",
  "3": "март",
  "4": "апрель",
  "5": "май",
  "6": "июнь",
  "7": "июль",
  "8": "август",
  "9": "сентябрь",
  "10": "октябрь",
  "11": "ноябрь",
  "12": "декабрь",
};

/** Тело строки плана-графика ПЭК: периодичность из программы, 1–60 месяцев. */
export type MonitoringPlanItemCreateInput = {
  source_id: string;
  substance: string;
  periodicity_months: number;
  next_due_on: string;
  method?: string | null;
  laboratory?: string | null;
  notes?: string | null;
};

/** Правка строки плана: источник не меняется — ручка его не принимает. */
export type MonitoringPlanItemUpdateInput = Omit<
  MonitoringPlanItemCreateInput,
  "source_id"
>;

/** Тело замера ПЭК: строка плана необязательна — замер бывает внеплановым. */
export type EmissionMeasurementCreateInput = {
  plan_id?: string | null;
  source_id: string;
  substance: string;
  measured_on: string;
  value_grams_per_second: string;
  protocol_number?: string | null;
  laboratory?: string | null;
  notes?: string | null;
};

/** Правка замера: источник, вещество и строка плана не меняются. */
export type EmissionMeasurementUpdateInput = {
  measured_on: string;
  value_grams_per_second: string;
  protocol_number?: string | null;
  laboratory?: string | null;
  notes?: string | null;
};

/** Тело точки водопользования: номер уникален в пределах объекта НВОС. */
export type WaterPointCreateInput = {
  facility_id: string;
  point_number: string;
  name: string;
  kind: string;
  water_body?: string | null;
  permit_number?: string | null;
  permit_valid_until?: string | null;
  annual_limit_cubic_meters?: string | null;
  notes?: string | null;
};

/** Правка точки: объект НВОС не меняется — ручка его не принимает. */
export type WaterPointUpdateInput = Omit<WaterPointCreateInput, "facility_id">;

/** Тело записи водопользования: единица учёта — месяц. */
export type WaterRecordCreateInput = {
  point_id: string;
  period_year: number;
  period_month: number;
  volume_cubic_meters: string;
  basis: string;
  meter_number?: string | null;
  notes?: string | null;
};

/** Правка записи: точка и период не меняются — это ключ записи. */
export type WaterRecordUpdateInput = {
  volume_cubic_meters: string;
  basis: string;
  meter_number?: string | null;
  notes?: string | null;
};

/** Тело записи журнала учёта отходов: масса больше нуля, дата не в будущем. */
export type WasteMovementCreateInput = {
  passport_id: string;
  kind: string;
  happened_on: string;
  quantity_tons: string;
  counterparty?: string | null;
  notes?: string | null;
};

export type WasteMovementUpdateInput = WasteMovementCreateInput;

/** Тело источника выбросов: номер уникален в пределах объекта НВОС. */
export type EmissionSourceCreateInput = {
  facility_id: string;
  source_number: string;
  name: string;
  kind: string;
  location?: string | null;
  inventoried_on?: string | null;
  notes?: string | null;
};

export type EmissionSourceUpdateInput = EmissionSourceCreateInput;

/** Тело норматива выброса: пустой срок разрешения — «бессрочно». */
export type EmissionNormCreateInput = {
  source_id: string;
  substance: string;
  limit_grams_per_second?: string | null;
  limit_tons_per_year?: string | null;
  permit_number?: string | null;
  valid_until?: string | null;
  notes?: string | null;
};

export type EmissionNormUpdateInput = EmissionNormCreateInput;

export type WasteMovementDto = {
  id: string;
  passport_id: string;
  kind: string;
  kind_label: string;
  happened_on: string;
  quantity_tons: string;
  contract_id?: string | null;
  counterparty?: string | null;
  notes?: string | null;
};

export const ecologyApi = {
  listFacilities: async (): Promise<EnvironmentalFacilityDto[]> => {
    const { data } = await apiClient.get<{
      items?: EnvironmentalFacilityDto[];
    }>("/ecology/facilities", { params: { limit: 200, offset: 0 } });
    return Array.isArray(data?.items) ? data.items : [];
  },

  listWastePassports: async (): Promise<WastePassportDto[]> => {
    const { data } = await apiClient.get<{ items?: WastePassportDto[] }>(
      "/ecology/waste-passports",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listWasteMovements: async (): Promise<WasteMovementDto[]> => {
    const { data } = await apiClient.get<{ items?: WasteMovementDto[] }>(
      "/ecology/waste-movements",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listEmissionSources: async (): Promise<EmissionSourceDto[]> => {
    const { data } = await apiClient.get<{ items?: EmissionSourceDto[] }>(
      "/ecology/emission-sources",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listEmissionNorms: async (): Promise<EmissionNormDto[]> => {
    const { data } = await apiClient.get<{ items?: EmissionNormDto[] }>(
      "/ecology/emission-norms",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listMonitoringPlan: async (): Promise<MonitoringPlanItemDto[]> => {
    const { data } = await apiClient.get<{ items?: MonitoringPlanItemDto[] }>(
      "/ecology/monitoring-plan",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listEmissionMeasurements: async (): Promise<EmissionMeasurementDto[]> => {
    const { data } = await apiClient.get<{ items?: EmissionMeasurementDto[] }>(
      "/ecology/emission-measurements",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listWaterPoints: async (): Promise<WaterPointDto[]> => {
    const { data } = await apiClient.get<{ items?: WaterPointDto[] }>(
      "/ecology/water-points",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listWaterRecords: async (): Promise<WaterRecordDto[]> => {
    const { data } = await apiClient.get<{ items?: WaterRecordDto[] }>(
      "/ecology/water-records",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listFeeRates: async (): Promise<FeeRateDto[]> => {
    const { data } = await apiClient.get<{ items?: FeeRateDto[] }>(
      "/ecology/fee-rates",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listFeeLines: async (): Promise<FeeLineDto[]> => {
    const { data } = await apiClient.get<{ items?: FeeLineDto[] }>(
      "/ecology/fee-lines",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listReportingDeadlines: async (): Promise<ReportingDeadlineDto[]> => {
    const { data } = await apiClient.get<{ items?: ReportingDeadlineDto[] }>(
      "/ecology/reporting-deadlines",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  createFacility: async (
    body: EnvironmentalFacilityCreateInput,
  ): Promise<EnvironmentalFacilityDto> => {
    const { data } = await apiClient.post<EnvironmentalFacilityDto>(
      "/ecology/facilities",
      body,
    );
    return data;
  },

  updateFacility: async (
    id: string,
    body: EnvironmentalFacilityUpdateInput,
  ): Promise<EnvironmentalFacilityDto> => {
    const { data } = await apiClient.patch<EnvironmentalFacilityDto>(
      `/ecology/facilities/${id}`,
      body,
    );
    return data;
  },

  createWastePassport: async (
    body: WastePassportCreateInput,
  ): Promise<WastePassportDto> => {
    const { data } = await apiClient.post<WastePassportDto>(
      "/ecology/waste-passports",
      body,
    );
    return data;
  },

  updateWastePassport: async (
    id: string,
    body: WastePassportUpdateInput,
  ): Promise<WastePassportDto> => {
    const { data } = await apiClient.patch<WastePassportDto>(
      `/ecology/waste-passports/${id}`,
      body,
    );
    return data;
  },

  createWasteMovement: async (
    body: WasteMovementCreateInput,
  ): Promise<WasteMovementDto> => {
    const { data } = await apiClient.post<WasteMovementDto>(
      "/ecology/waste-movements",
      body,
    );
    return data;
  },

  updateWasteMovement: async (
    id: string,
    body: WasteMovementUpdateInput,
  ): Promise<WasteMovementDto> => {
    const { data } = await apiClient.patch<WasteMovementDto>(
      `/ecology/waste-movements/${id}`,
      body,
    );
    return data;
  },

  createEmissionSource: async (
    body: EmissionSourceCreateInput,
  ): Promise<EmissionSourceDto> => {
    const { data } = await apiClient.post<EmissionSourceDto>(
      "/ecology/emission-sources",
      body,
    );
    return data;
  },

  updateEmissionSource: async (
    id: string,
    body: EmissionSourceUpdateInput,
  ): Promise<EmissionSourceDto> => {
    const { data } = await apiClient.patch<EmissionSourceDto>(
      `/ecology/emission-sources/${id}`,
      body,
    );
    return data;
  },

  createEmissionNorm: async (
    body: EmissionNormCreateInput,
  ): Promise<EmissionNormDto> => {
    const { data } = await apiClient.post<EmissionNormDto>(
      "/ecology/emission-norms",
      body,
    );
    return data;
  },

  updateEmissionNorm: async (
    id: string,
    body: EmissionNormUpdateInput,
  ): Promise<EmissionNormDto> => {
    const { data } = await apiClient.patch<EmissionNormDto>(
      `/ecology/emission-norms/${id}`,
      body,
    );
    return data;
  },

  createMonitoringPlanItem: async (
    body: MonitoringPlanItemCreateInput,
  ): Promise<MonitoringPlanItemDto> => {
    const { data } = await apiClient.post<MonitoringPlanItemDto>(
      "/ecology/monitoring-plan",
      body,
    );
    return data;
  },

  updateMonitoringPlanItem: async (
    id: string,
    body: MonitoringPlanItemUpdateInput,
  ): Promise<MonitoringPlanItemDto> => {
    const { data } = await apiClient.patch<MonitoringPlanItemDto>(
      `/ecology/monitoring-plan/${id}`,
      body,
    );
    return data;
  },

  createEmissionMeasurement: async (
    body: EmissionMeasurementCreateInput,
  ): Promise<EmissionMeasurementDto> => {
    const { data } = await apiClient.post<EmissionMeasurementDto>(
      "/ecology/emission-measurements",
      body,
    );
    return data;
  },

  updateEmissionMeasurement: async (
    id: string,
    body: EmissionMeasurementUpdateInput,
  ): Promise<EmissionMeasurementDto> => {
    const { data } = await apiClient.patch<EmissionMeasurementDto>(
      `/ecology/emission-measurements/${id}`,
      body,
    );
    return data;
  },

  createWaterPoint: async (
    body: WaterPointCreateInput,
  ): Promise<WaterPointDto> => {
    const { data } = await apiClient.post<WaterPointDto>(
      "/ecology/water-points",
      body,
    );
    return data;
  },

  updateWaterPoint: async (
    id: string,
    body: WaterPointUpdateInput,
  ): Promise<WaterPointDto> => {
    const { data } = await apiClient.patch<WaterPointDto>(
      `/ecology/water-points/${id}`,
      body,
    );
    return data;
  },

  createWaterRecord: async (
    body: WaterRecordCreateInput,
  ): Promise<WaterRecordDto> => {
    const { data } = await apiClient.post<WaterRecordDto>(
      "/ecology/water-records",
      body,
    );
    return data;
  },

  updateWaterRecord: async (
    id: string,
    body: WaterRecordUpdateInput,
  ): Promise<WaterRecordDto> => {
    const { data } = await apiClient.patch<WaterRecordDto>(
      `/ecology/water-records/${id}`,
      body,
    );
    return data;
  },

  createFeeRate: async (body: FeeRateCreateInput): Promise<FeeRateDto> => {
    const { data } = await apiClient.post<FeeRateDto>(
      "/ecology/fee-rates",
      body,
    );
    return data;
  },

  updateFeeRate: async (
    id: string,
    body: FeeRateUpdateInput,
  ): Promise<FeeRateDto> => {
    const { data } = await apiClient.patch<FeeRateDto>(
      `/ecology/fee-rates/${id}`,
      body,
    );
    return data;
  },

  createFeeLine: async (body: FeeLineCreateInput): Promise<FeeLineDto> => {
    const { data } = await apiClient.post<FeeLineDto>(
      "/ecology/fee-lines",
      body,
    );
    return data;
  },

  updateFeeLine: async (
    id: string,
    body: FeeLineUpdateInput,
  ): Promise<FeeLineDto> => {
    const { data } = await apiClient.patch<FeeLineDto>(
      `/ecology/fee-lines/${id}`,
      body,
    );
    return data;
  },

  createReportingDeadline: async (
    body: ReportingDeadlineCreateInput,
  ): Promise<ReportingDeadlineDto> => {
    const { data } = await apiClient.post<ReportingDeadlineDto>(
      "/ecology/reporting-deadlines",
      body,
    );
    return data;
  },

  updateReportingDeadline: async (
    id: string,
    body: ReportingDeadlineUpdateInput,
  ): Promise<ReportingDeadlineDto> => {
    const { data } = await apiClient.patch<ReportingDeadlineDto>(
      `/ecology/reporting-deadlines/${id}`,
      body,
    );
    return data;
  },

  readiness: async (): Promise<EcologyReadinessDto> => {
    const { data } =
      await apiClient.get<EcologyReadinessDto>("/ecology/readiness");
    return data;
  },
};
