import { apiClient } from "@/api/client";

/**
 * Контур ПБ (Доп. №1 разд. 54.1): первичные средства и системы защиты.
 *
 * Ручки гейтятся модулем `fire_safety`: у арендатора без выдачи — 404, у
 * выдававшегося-отключённого чтение остаётся (read-only, BIZ-61).
 */

export type FireEquipmentKind =
  | "extinguisher"
  | "hydrant"
  | "shield"
  | "alarm_system"
  | "suppression_system"
  | "warning_system";

/** Подписи видов — словами, а не кодами: экран читает человек. */
export const FIRE_EQUIPMENT_TITLES: Record<FireEquipmentKind, string> = {
  extinguisher: "Огнетушитель",
  hydrant: "Пожарный кран",
  shield: "Пожарный щит",
  alarm_system: "Сигнализация (АУПС)",
  suppression_system: "Пожаротушение (АУПТ)",
  warning_system: "Оповещение (СОУЭ)",
};

export type FireEquipmentDto = {
  id: string;
  kind: string;
  label: string;
  site_id?: string | null;
  location?: string | null;
  recharge_due?: string | null;
  inspection_due?: string | null;
  status: string;
};

export type FireReadinessDto = {
  total_units: number;
  overdue_recharge: number;
  overdue_inspection: number;
  due_soon: number;
  due_soon_days: number;
};

export const fireSafetyApi = {
  listEquipment: async (): Promise<FireEquipmentDto[]> => {
    const { data } = await apiClient.get<{ items?: FireEquipmentDto[] }>(
      "/fire-safety/equipment",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  readiness: async (): Promise<FireReadinessDto> => {
    const { data } = await apiClient.get<FireReadinessDto>(
      "/fire-safety/readiness",
    );
    return data;
  },
};
