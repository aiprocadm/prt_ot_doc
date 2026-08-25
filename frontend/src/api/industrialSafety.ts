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
  /** Разд. 54.2: считаются только эксплуатируемые устройства. */
  total_devices: number;
  epb_overdue: number;
  epb_due_soon: number;
  /**
   * ФАКТ: назначенный срок службы истёк, действующего заключения ЭПБ нет.
   * ГРАНИЦА: платформа НЕ решает, обязана ли экспертиза быть проведена —
   * это зависит от типа устройства, документации и норм ФНП.
   */
  devices_past_lifetime_without_epb: number;
};

export type TechnicalDeviceDto = {
  id: string;
  facility_id: string;
  kind: string;
  kind_label: string;
  name: string;
  serial_number?: string | null;
  commissioned_on?: string | null;
  lifetime_until?: string | null;
  epb_conclusion_number?: string | null;
  epb_registered_on?: string | null;
  epb_valid_until?: string | null;
  status: string;
  status_label: string;
  notes?: string | null;
  /** ok | due_soon | overdue | absent — «нет заключения» отдельное состояние. */
  epb_status: string;
  epb_status_label: string;
  past_lifetime: boolean;
};

export const industrialSafetyApi = {
  listFacilities: async (): Promise<HazardousFacilityDto[]> => {
    const { data } = await apiClient.get<{ items?: HazardousFacilityDto[] }>(
      "/industrial-safety/facilities",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listDevices: async (): Promise<TechnicalDeviceDto[]> => {
    const { data } = await apiClient.get<{ items?: TechnicalDeviceDto[] }>(
      "/industrial-safety/devices",
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
