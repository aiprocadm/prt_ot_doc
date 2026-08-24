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
  /** Разд. 54.1 «контроль сроков»: просроченные противопожарные инструктажи. */
  overdue_fire_briefings: number;
  /** Разд. 54.1 «Тренировки и учения»: план прошёл, факта нет. */
  overdue_drills: number;
  /** Назначено вперёд — не просрочка, но пустой план-график видно. */
  planned_drills: number;
  last_drill_on?: string | null;
  /**
   * Сколько дней с последней тренировки. ГРАНИЦА: интервал «не реже раза в
   * полгода» (ППР РФ) обязателен для объектов с массовым пребыванием людей, а
   * признака массового пребывания в данных нет — экран показывает факт и НЕ
   * называет это нарушением.
   */
  days_since_last_drill?: number | null;
};

export type FireDrillDto = {
  id: string;
  kind: string;
  /** Вид словами — перевод делает сервер, экран его не дублирует. */
  kind_label: string;
  title: string;
  planned_on: string;
  held_on?: string | null;
  site_id?: string | null;
  scenario?: string | null;
  participants?: number | null;
  outcome?: string | null;
  outcome_label?: string | null;
  findings?: string | null;
  /** planned | held | overdue — считается сервером при чтении. */
  status: string;
};

export const fireSafetyApi = {
  listEquipment: async (): Promise<FireEquipmentDto[]> => {
    const { data } = await apiClient.get<{ items?: FireEquipmentDto[] }>(
      "/fire-safety/equipment",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listDrills: async (): Promise<FireDrillDto[]> => {
    const { data } = await apiClient.get<{ items?: FireDrillDto[] }>(
      "/fire-safety/drills",
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
