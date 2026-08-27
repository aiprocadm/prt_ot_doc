import { apiClient } from "@/api/client";

/**
 * Контур ГО и ЧС (Доп. №1 разд. 56.1, срез-1): нештатные формирования.
 *
 * ГРАНИЦА: платформа не решает, обязана ли организация создавать формирования
 * и сколько их нужно — это категория организации по ГО и решения органа
 * управления ГОЧС. Полей «требуется» и «недоукомплектовано» в ответах нет.
 */
export type FormationDto = {
  id: string;
  name: string;
  kind: string;
  kind_label: string;
  purpose?: string | null;
  commander_person_id?: string | null;
  /** ФИО из ядра; null — командир не назначен. */
  commander_name?: string | null;
  equipment_notes?: string | null;
  notes?: string | null;
  /** Действующие члены состава (без выведенных). */
  members_active: number;
};

export type CivilDefenseReadinessDto = {
  total_formations: number;
  by_kind: Record<string, number>;
  without_commander: number;
  members_active: number;
  /** Разд. 56.1 «учения»: план-график и журнал проведённых. */
  drills_total: number;
  drills_overdue: number;
  drills_held_this_year: number;
};

export type DrillDto = {
  id: string;
  kind: string;
  kind_label: string;
  title: string;
  planned_on: string;
  held_on?: string | null;
  formation_id?: string | null;
  /** Название формирования; null — учение общеобъектовое. */
  formation_name?: string | null;
  site_id?: string | null;
  scenario?: string | null;
  participants?: number | null;
  outcome?: string | null;
  outcome_label?: string | null;
  findings?: string | null;
  /** planned | held | overdue — считается при чтении по датам. */
  status: string;
  status_label: string;
};

export const civilDefenseApi = {
  listFormations: async (): Promise<FormationDto[]> => {
    const { data } = await apiClient.get<{ items?: FormationDto[] }>(
      "/civil-defense/formations",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listDrills: async (): Promise<DrillDto[]> => {
    const { data } = await apiClient.get<{ items?: DrillDto[] }>(
      "/civil-defense/drills",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  readiness: async (): Promise<CivilDefenseReadinessDto> => {
    const { data } = await apiClient.get<CivilDefenseReadinessDto>(
      "/civil-defense/readiness",
    );
    return data;
  },
};
