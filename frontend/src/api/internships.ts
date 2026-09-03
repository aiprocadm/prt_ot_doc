import { apiClient } from "@/api/client";

/**
 * Стажировки на рабочем месте (Доп. №1 разд. 56.2, срез-7 → общий экран).
 *
 * Сущность ЯДРОВАЯ: стажировку печатает первичный инструктаж НОВОГО
 * РАБОТНИКА — по охране труда, любому рабочему, а не только водителю.
 * Контур дисциплины (БДД) показывает свои счётчики по разметке, а реестр
 * живёт здесь, один на все дисциплины.
 *
 * ГРАНИЦА: полей «требуется ли стажировка», «достаточно ли смен» и «допущен
 * ли к самостоятельной работе» нет. Недобор — ФАКТ расхождения плана и
 * факта, а не вердикт о законности допуска.
 */
export type InternshipDto = {
  id: string;
  person_id: string;
  /** ФИО из ядрового справочника людей — в записи не хранится */
  person_name: string;
  mentor_person_id?: string | null;
  /** пусто — наставник НЕ НАЗНАЧЕН, а не «неизвестен» */
  mentor_name?: string | null;
  /** код дисциплины из общего словаря; пусто — «не размечено» */
  discipline?: string | null;
  discipline_label?: string | null;
  subject?: string | null;
  planned_shifts: number;
  completed_shifts: number;
  /** считается сервером: сколько смен осталось до плана */
  shifts_remaining: number;
  /**
   * Считается сервером: ЗАВЕРШЕНА, а смен меньше плана — формально закрытая
   * стажировка, которой по сменам не было. Факт расхождения, не приговор.
   */
  completed_short: boolean;
  started_on?: string | null;
  finished_on?: string | null;
  status: string;
  status_label: string;
  notes?: string | null;
};

/**
 * Плитки шапки. Считаются СЕРВЕРОМ по всем записям арендатора, а не по
 * загруженной странице списка: «всего» по первым двумстам строкам врало бы
 * ровно у тех, у кого стажировок много.
 */
export type InternshipSummaryDto = {
  total: number;
  by_status: Record<string, number>;
  /** завершённые с недобором смен — ФАКТ расхождения, а не вердикт */
  completed_short: number;
  /** назначенные или идущие БЕЗ наставника — некому подтвердить смены */
  active_without_mentor: number;
};

/**
 * Состояния стажировки словами.
 *
 * Словарь написан РУКАМИ и обязан совпадать с ``INTERNSHIP_STATUSES`` бэкенда
 * (app.models.training). Держит его тест-сторож tests/test_internships.py:
 * не обнови этот файл — состояние нельзя будет выбрать в форме (тот же класс
 * дрейфа, что словарь дисциплин в training.ts).
 */
export const INTERNSHIP_STATUS_TITLES: Record<string, string> = {
  planned: "Назначена",
  in_progress: "Идёт",
  completed: "Завершена",
  cancelled: "Отменена",
};

export type InternshipListParams = {
  status?: string;
  discipline?: string;
  person_id?: string;
};

export type InternshipCreatePayload = {
  person_id: string;
  mentor_person_id?: string | null;
  discipline?: string | null;
  subject?: string | null;
  planned_shifts: number;
  completed_shifts: number;
  started_on?: string | null;
  finished_on?: string | null;
  status: string;
  notes?: string | null;
};

/** Стажёра сменить нельзя — это стажировка другого человека. */
export type InternshipUpdatePayload = Omit<
  Partial<InternshipCreatePayload>,
  "person_id"
>;

export const internshipsApi = {
  list: async (params: InternshipListParams = {}): Promise<InternshipDto[]> => {
    const query: Record<string, string | number> = { limit: 200, offset: 0 };
    if (params.status) query.status = params.status;
    if (params.discipline) query.discipline = params.discipline;
    if (params.person_id) query.person_id = params.person_id;
    const { data } = await apiClient.get<{ items?: InternshipDto[] }>(
      "/internships",
      { params: query },
    );
    return Array.isArray(data?.items) ? data.items : [];
  },

  summary: async (): Promise<InternshipSummaryDto> => {
    const { data } = await apiClient.get<InternshipSummaryDto>(
      "/internships/summary",
    );
    return data;
  },

  create: async (payload: InternshipCreatePayload): Promise<InternshipDto> => {
    const { data } = await apiClient.post<InternshipDto>(
      "/internships",
      payload,
    );
    return data;
  },

  update: async (
    id: string,
    payload: InternshipUpdatePayload,
  ): Promise<InternshipDto> => {
    const { data } = await apiClient.patch<InternshipDto>(
      `/internships/${encodeURIComponent(id)}`,
      payload,
    );
    return data;
  },
};
