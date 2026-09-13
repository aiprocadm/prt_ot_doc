import { apiClient } from "@/api/client";

/**
 * Виды проверки — ровно те, что принимает сервер (`InspectionType` в
 * `backend/app/models/inspections.py`), и в том же порядке (срез-150).
 *
 * До среза экран проверок предлагал пять значений («Плановая»,
 * «Внеплановая», «Документарная», «Выездная», «Встречная»), которых у сервера
 * нет ни одного: пересечение с `internal`/`external` было ПУСТЫМ, и завести
 * проверку через форму было невозможно — любой выбор давал 422. Вдобавок
 * список подмешивал статусы («Плановая» — это `planned`, статус проверки).
 * Состав сверяет сторож `tests/test_incident_inspection_vocab.py`.
 */
export const INSPECTION_TYPE_LABELS: Record<string, string> = {
  internal: "Внутренняя",
  external: "Внешняя (надзорная)",
};

export const INSPECTION_TYPES: readonly string[] = Object.keys(
  INSPECTION_TYPE_LABELS,
);

/** Статусы проверки — словарь сервера (`InspectionStatus`), включая отменённую. */
export const INSPECTION_STATUS_LABELS: Record<string, string> = {
  planned: "Запланирована",
  in_progress: "В работе",
  completed: "Завершена",
  cancelled: "Отменена",
};

export const INSPECTION_STATUSES: readonly string[] = Object.keys(
  INSPECTION_STATUS_LABELS,
);

export type InspectionResult = {
  id: string;
  inspection_id: string;
  title: string;
  outcome: string | null;
  notes: string | null;
  issued_at: string | null;
  file_id: string | null;
  created_at: string;
};

export type Inspection = {
  id: string;
  company_id: string;
  site_id: string | null;
  inspection_type: string;
  responsible_id: string | null;
  recurrence_rule: string | null;
  authority: string;
  purpose: string | null;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  result_summary: string | null;
  results: InspectionResult[];
};

export type InspectionPage = {
  items: Inspection[];
  total: number;
};

export const inspectionsApi = {
  list: async (params?: {
    company_id?: string;
    site_id?: string;
    status_filter?: string;
    inspection_type?: string;
    responsible_id?: string;
    limit?: number;
    offset?: number;
  }) => {
    const { data } = await apiClient.get<InspectionPage>("/inspections", {
      params,
    });
    return data;
  },
  listResults: async (inspectionId: string) => {
    const { data } = await apiClient.get<InspectionResult[]>(
      `/inspections/${inspectionId}/results`,
    );
    return data;
  },
  create: async (payload: {
    company_id: string;
    site_id?: string;
    inspection_type: string;
    authority: string;
    purpose?: string;
    scheduled_at?: string;
  }) => {
    const { data } = await apiClient.post<Inspection>("/inspections", payload);
    return data;
  },
};
