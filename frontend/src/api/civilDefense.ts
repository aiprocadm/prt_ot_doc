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
  /** Разд. 56.1 «категорирование и планирование». */
  profiles_total: number;
  profiles_by_category: Record<string, number>;
  planning_documents: number;
  planning_review_overdue: number;
  /** Разд. 56.1 «программы обучения»: программы ЯДРА с дисциплиной ГО. */
  training_programs: number;
  /** Доп. №1 разд. 57.4: открытые происшествия этой дисциплины (срез-49). */
  incidents_open: number;
};

/**
 * Учебная программа, размеченная дисциплиной ГО.
 *
 * ТОЛЬКО ЧТЕНИЕ: реестром программ владеет раздел обучения — второй вход в
 * него означал бы два места правды.
 */
export type TrainingProgramDto = {
  id: string;
  title: string;
  code?: string | null;
  duration_hours?: number | null;
  valid_period_days?: number | null;
};

export type ProfileDto = {
  id: string;
  site_id: string;
  site_name?: string | null;
  category: string;
  category_label: string;
  decision_number?: string | null;
  decision_date?: string | null;
  responsible?: string | null;
  notes?: string | null;
};

export type CdDocumentDto = {
  id: string;
  kind: string;
  kind_label: string;
  title: string;
  number?: string | null;
  site_id?: string | null;
  approved_on?: string | null;
  review_due?: string | null;
  responsible?: string | null;
  notes?: string | null;
  /** ok | due_soon | overdue — пустой срок означает «бессрочно». */
  review_status: string;
  review_status_label: string;
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

  listProfiles: async (): Promise<ProfileDto[]> => {
    const { data } = await apiClient.get<{ items?: ProfileDto[] }>(
      "/civil-defense/profiles",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listDocuments: async (): Promise<CdDocumentDto[]> => {
    const { data } = await apiClient.get<{ items?: CdDocumentDto[] }>(
      "/civil-defense/documents",
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  listTrainingPrograms: async (): Promise<TrainingProgramDto[]> => {
    const { data } = await apiClient.get<{ items?: TrainingProgramDto[] }>(
      "/civil-defense/training-programs",
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
