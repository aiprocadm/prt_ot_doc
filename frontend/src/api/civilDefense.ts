import { apiClient } from "@/api/client";

/**
 * Контур ГО и ЧС (Доп. №1 разд. 56.1, срез-1): нештатные формирования.
 *
 * ГРАНИЦА: платформа не решает, обязана ли организация создавать формирования
 * и сколько их нужно — это категория организации по ГО и решения органа
 * управления ГОЧС. Полей «требуется» и «недоукомплектовано» в ответах нет.
 */
/** Виды формирований — копия `CD_FORMATION_KINDS` бэкенда (срез-109). */
export const CD_FORMATION_KIND_TITLES: Record<string, string> = {
  nasf: "НАСФ (аварийно-спасательное формирование)",
  nfgo: "НФГО (формирование по обеспечению ГО)",
};

/** Виды учений и тренировок — копия `CD_DRILL_KINDS` бэкенда. */
export const CD_DRILL_KIND_TITLES: Record<string, string> = {
  command_staff: "Командно-штабное учение",
  tactical_special: "Тактико-специальное учение",
  complex: "Комплексное учение",
  facility_training: "Объектовая тренировка",
};

/** Результаты проведённого учения — копия `CD_DRILL_OUTCOMES` бэкенда. */
export const CD_DRILL_OUTCOME_TITLES: Record<string, string> = {
  passed: "Проведено, задачи выполнены",
  with_remarks: "Проведено с замечаниями",
  failed: "Задачи не выполнены",
};

/** Категории объекта по ГО — копия `CD_GO_CATEGORIES` бэкенда (срез-110). */
export const CD_GO_CATEGORY_TITLES: Record<string, string> = {
  special: "Объект особой важности",
  first: "Первая категория по ГО",
  second: "Вторая категория по ГО",
  none: "Категория не присвоена",
};

/** Виды документов планирования ГО — копия `CD_DOCUMENT_KINDS` бэкенда. */
export const CD_DOCUMENT_KIND_TITLES: Record<string, string> = {
  plan_go: "План гражданской обороны",
  plan_emergency: "План действий по предупреждению и ликвидации ЧС",
  safety_passport: "Паспорт безопасности объекта",
  order: "Приказ",
  regulation: "Положение",
  instruction: "Инструкция",
};

/** Строка состава формирования: ФИО из ядра, вывод — дата, а не удаление. */
export type FormationMemberDto = {
  id: string;
  formation_id: string;
  person_id: string;
  person_name: string;
  role_in_formation?: string | null;
  assigned_on?: string | null;
  released_on?: string | null;
  notes?: string | null;
  /** active | released — считается при чтении по дате вывода. */
  status: string;
  status_label: string;
};

/** Тело сведений по ГО об объекте: категорирование выполняет орган. */
export type ProfileCreateInput = {
  site_id: string;
  category: string;
  decision_number?: string | null;
  decision_date?: string | null;
  responsible?: string | null;
  notes?: string | null;
};

/** Правка сведений: площадку не меняют — это сведения другого объекта. */
export type ProfileUpdateInput = Omit<ProfileCreateInput, "site_id">;

/** Тело документа планирования ГО. */
export type CdDocumentCreateInput = {
  kind: string;
  title: string;
  number?: string | null;
  site_id?: string | null;
  approved_on?: string | null;
  review_due?: string | null;
  responsible?: string | null;
  notes?: string | null;
};

export type CdDocumentUpdateInput = CdDocumentCreateInput;

/** Тело формирования: вид из закрытого словаря, командир — человек из ядра. */
export type FormationCreateInput = {
  name: string;
  kind: string;
  purpose?: string | null;
  commander_person_id?: string | null;
  equipment_notes?: string | null;
  notes?: string | null;
};

export type FormationUpdateInput = FormationCreateInput;

/** Тело строки состава: человек из ядра, роль — свободная строка. */
export type FormationMemberCreateInput = {
  person_id: string;
  role_in_formation?: string | null;
  assigned_on?: string | null;
  notes?: string | null;
};

/** Правка строки состава: `released_on: null` возвращает человека в состав. */
export type FormationMemberUpdateInput = {
  role_in_formation?: string | null;
  assigned_on?: string | null;
  released_on?: string | null;
  notes?: string | null;
};

/** Тело учения: план обязателен — учение рождается запланированным. */
export type DrillCreateInput = {
  kind: string;
  title: string;
  planned_on: string;
  formation_id?: string | null;
  site_id?: string | null;
  scenario?: string | null;
  participants?: number | null;
  notes?: string | null;
};

/** Правка учения: сюда же вносится протокол — дата, результат и анализ. */
export type DrillUpdateInput = DrillCreateInput & {
  held_on?: string | null;
  outcome?: string | null;
  findings?: string | null;
};

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
  listFormationMembers: async (
    formationId: string,
  ): Promise<FormationMemberDto[]> => {
    const { data } = await apiClient.get<{ items?: FormationMemberDto[] }>(
      `/civil-defense/formations/${formationId}/members`,
      { params: { limit: 200, offset: 0 } },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  createProfile: async (body: ProfileCreateInput): Promise<ProfileDto> => {
    const { data } = await apiClient.post<ProfileDto>(
      "/civil-defense/profiles",
      body,
    );
    return data;
  },

  updateProfile: async (
    id: string,
    body: ProfileUpdateInput,
  ): Promise<ProfileDto> => {
    const { data } = await apiClient.patch<ProfileDto>(
      `/civil-defense/profiles/${id}`,
      body,
    );
    return data;
  },

  createDocument: async (
    body: CdDocumentCreateInput,
  ): Promise<CdDocumentDto> => {
    const { data } = await apiClient.post<CdDocumentDto>(
      "/civil-defense/documents",
      body,
    );
    return data;
  },

  updateDocument: async (
    id: string,
    body: CdDocumentUpdateInput,
  ): Promise<CdDocumentDto> => {
    const { data } = await apiClient.patch<CdDocumentDto>(
      `/civil-defense/documents/${id}`,
      body,
    );
    return data;
  },

  createFormation: async (
    body: FormationCreateInput,
  ): Promise<FormationDto> => {
    const { data } = await apiClient.post<FormationDto>(
      "/civil-defense/formations",
      body,
    );
    return data;
  },

  updateFormation: async (
    id: string,
    body: FormationUpdateInput,
  ): Promise<FormationDto> => {
    const { data } = await apiClient.patch<FormationDto>(
      `/civil-defense/formations/${id}`,
      body,
    );
    return data;
  },

  addFormationMember: async (
    formationId: string,
    body: FormationMemberCreateInput,
  ): Promise<unknown> => {
    const { data } = await apiClient.post<unknown>(
      `/civil-defense/formations/${formationId}/members`,
      body,
    );
    return data;
  },

  updateFormationMember: async (
    formationId: string,
    memberId: string,
    body: FormationMemberUpdateInput,
  ): Promise<unknown> => {
    const { data } = await apiClient.patch<unknown>(
      `/civil-defense/formations/${formationId}/members/${memberId}`,
      body,
    );
    return data;
  },

  createDrill: async (body: DrillCreateInput): Promise<DrillDto> => {
    const { data } = await apiClient.post<DrillDto>(
      "/civil-defense/drills",
      body,
    );
    return data;
  },

  updateDrill: async (
    id: string,
    body: DrillUpdateInput,
  ): Promise<DrillDto> => {
    const { data } = await apiClient.patch<DrillDto>(
      `/civil-defense/drills/${id}`,
      body,
    );
    return data;
  },

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
