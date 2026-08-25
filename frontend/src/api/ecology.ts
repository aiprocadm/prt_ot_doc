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
};

export const ecologyApi = {
  listFacilities: async (): Promise<EnvironmentalFacilityDto[]> => {
    const { data } = await apiClient.get<{
      items?: EnvironmentalFacilityDto[];
    }>("/ecology/facilities", { params: { limit: 200, offset: 0 } });
    return Array.isArray(data?.items) ? data.items : [];
  },

  readiness: async (): Promise<EcologyReadinessDto> => {
    const { data } =
      await apiClient.get<EcologyReadinessDto>("/ecology/readiness");
    return data;
  },
};
