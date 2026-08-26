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

  readiness: async (): Promise<EcologyReadinessDto> => {
    const { data } =
      await apiClient.get<EcologyReadinessDto>("/ecology/readiness");
    return data;
  },
};
