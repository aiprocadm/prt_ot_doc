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
  | "warning_system"
  | "fire_escape"
  | "water_supply";

/** Подписи видов — словами, а не кодами: экран читает человек. */
export const FIRE_EQUIPMENT_TITLES: Record<FireEquipmentKind, string> = {
  extinguisher: "Огнетушитель",
  hydrant: "Пожарный кран",
  shield: "Пожарный щит",
  alarm_system: "Сигнализация (АУПС)",
  suppression_system: "Пожаротушение (АУПТ)",
  warning_system: "Оповещение (СОУЭ)",
  // Разд. 54.1 «испытания (напр., пожарные лестницы, водопровод)».
  fire_escape: "Пожарная лестница",
  water_supply: "Противопожарный водопровод",
};

/** Подписи результатов работ — словами, перевод делает сервер, это запас. */
export const FIRE_MAINTENANCE_RESULT_TITLES: Record<string, string> = {
  passed: "Исправно",
  with_remarks: "Исправно с замечаниями",
  failed: "Неисправно",
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
  /** Последняя подтверждённая работа: срок без неё — обещание, не доказательство. */
  last_maintenance_on?: string | null;
  last_maintenance_result?: string | null;
};

export type FireDocumentDto = {
  id: string;
  kind: string;
  kind_label: string;
  title: string;
  site_id?: string | null;
  number?: string | null;
  location?: string | null;
  approved_on?: string | null;
  review_due?: string | null;
  responsible?: string | null;
  document_id?: string | null;
  notes?: string | null;
  /** ok | due_soon | overdue — считает сервер ядровым классификатором. */
  status: string;
  status_label: string;
};

export type FireMaintenanceDto = {
  id: string;
  equipment_id: string;
  kind: string;
  kind_label: string;
  performed_on: string;
  result: string;
  result_label: string;
  performer?: string | null;
  notes?: string | null;
  next_due?: string | null;
  /** Перенесла ли работа срок; «неисправно» не переносит. */
  shifted_due: boolean;
};

export type FireReadinessDto = {
  total_units: number;
  overdue_recharge: number;
  overdue_inspection: number;
  due_soon: number;
  due_soon_days: number;
  /** Разд. 54.1 «контроль сроков»: просроченные противопожарные инструктажи. */
  overdue_fire_briefings: number;
  /**
   * Разд. 54.1 «Документы ПБ»: сколько карточек заведено и у скольких
   * просрочен пересмотр. ГРАНИЦА: сколько документов ОБЯЗАТЕЛЬНО, платформа
   * не судит — применимость нормы из данных не следует.
   */
  fire_documents: number;
  overdue_documents: number;
  /** Разд. 54.1 «регламентные работы»: средства без единой записи о работе. */
  units_without_maintenance: number;
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

  listDocuments: async (): Promise<FireDocumentDto[]> => {
    const { data } = await apiClient.get<{ items?: FireDocumentDto[] }>(
      "/fire-safety/documents",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listMaintenance: async (
    equipmentId?: string,
  ): Promise<FireMaintenanceDto[]> => {
    const { data } = await apiClient.get<{ items?: FireMaintenanceDto[] }>(
      "/fire-safety/maintenance",
      {
        params: {
          limit: 200,
          offset: 0,
          ...(equipmentId ? { equipment_id: equipmentId } : {}),
        },
      },
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
