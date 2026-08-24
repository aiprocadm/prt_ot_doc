import { apiClient } from "@/api/client";

/**
 * Контур ПромБеза (Доп. №1 разд. 54.2): реестр опасных производственных
 * объектов.
 *
 * Ручки гейтятся модулем `industrial_safety`: у арендатора без выдачи — 404, у
 * выдававшегося-отключённого чтение остаётся (read-only, BIZ-61).
 */

export type OpoHazardClass = "I" | "II" | "III" | "IV";

/**
 * Подписи классов — словами. Сервер отдаёт готовую подпись в `hazard_class_label`,
 * это запас для мест, где на руках только код (например, разрез сводки).
 */
export const OPO_HAZARD_CLASS_TITLES: Record<string, string> = {
  I: "I класс — чрезвычайно высокая опасность",
  II: "II класс — высокая опасность",
  III: "III класс — средняя опасность",
  IV: "IV класс — низкая опасность",
};

export type HazardousFacilityDto = {
  id: string;
  name: string;
  register_number: string;
  hazard_class: string;
  hazard_class_label: string;
  site_id?: string | null;
  registered_on?: string | null;
  excluded_on?: string | null;
  status: string;
  status_label: string;
  responsible?: string | null;
  notes?: string | null;
};

export type IndustrialReadinessDto = {
  total_facilities: number;
  /** Класс → число ДЕЙСТВУЮЩИХ объектов; ключи всегда все четыре. */
  by_class: Record<string, number>;
  excluded_facilities: number;
};

export const industrialSafetyApi = {
  listFacilities: async (): Promise<HazardousFacilityDto[]> => {
    const { data } = await apiClient.get<{ items?: HazardousFacilityDto[] }>(
      "/industrial-safety/facilities",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  readiness: async (): Promise<IndustrialReadinessDto> => {
    const { data } = await apiClient.get<IndustrialReadinessDto>(
      "/industrial-safety/readiness",
    );
    return data;
  },
};
