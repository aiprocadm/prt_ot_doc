import { apiClient } from "@/api/client";

/**
 * Слово фильтра «без разметки» у сервера (срез-65): `?discipline=none` отдаёт
 * только неразмеченные происшествия. Записать «none» дисциплиной нельзя —
 * снятие разметки по-прежнему null.
 */
export const UNMARKED_DISCIPLINE_FILTER = "none";

/**
 * Слово фильтра «только открытые» у сервера (срез-68): `?status_filter=open`
 * отдаёт не закрытые и не отменённые — той же формулой, что отчёты считают
 * «открытых происшествий». Ссылка из отчёта ведёт к тем же записям.
 */
export const OPEN_STATUS_FILTER = "open";

/** Подписи статусов происшествия — словарь сервера (`IncidentStatus`). */
export const INCIDENT_STATUS_LABELS: Record<string, string> = {
  reported: "Сообщено",
  investigating: "Расследуется",
  corrective_actions: "Корректирующие действия",
  closed: "Закрыт",
  cancelled: "Отменён",
};

/**
 * Виды происшествия — ровно те, что принимает сервер (`IncidentType` в
 * `backend/app/models/incidents.py`), и в том же порядке (срез-150).
 *
 * До среза экран происшествий держал собственный список из семи значений
 * («Травма», «Смертельный случай», «Пожар», «Экологический инцидент»…), из
 * которых сервер принимал ровно одно: остальные приводили к 422, а
 * «Несчастный случай» — основной вид записи — завести было нельзя вовсе.
 * Словарь один на все экраны (реестр происшествий, карточка сотрудника), и
 * его состав сверяет сторож `tests/test_incident_inspection_vocab.py`.
 */
export const INCIDENT_TYPE_LABELS: Record<string, string> = {
  accident: "Несчастный случай",
  microtrauma: "Микротравма",
  near_miss: "Опасное событие",
  unsafe_condition: "Опасное состояние",
};

export const INCIDENT_TYPES: readonly string[] =
  Object.keys(INCIDENT_TYPE_LABELS);

/** Тяжесть происшествия — словарь сервера (`IncidentSeverity`); `critical` у него нет. */
export const INCIDENT_SEVERITY_LABELS: Record<string, string> = {
  low: "Низкая",
  medium: "Средняя",
  high: "Высокая",
};

export const INCIDENT_SEVERITIES: readonly string[] = Object.keys(
  INCIDENT_SEVERITY_LABELS,
);

export type Incident = {
  id: string;
  title: string;
  description: string | null;
  incident_type: string;
  occurred_at: string;
  company_id: string;
  site_id: string;
  severity: string;
  status: string;
  investigation_stage: string;
  location_description: string | null;
  pack_id: string | null;
  victim_ids: string[];
  /** Код дисциплины из общего словаря; null — «не размечено», а НЕ «охрана труда». */
  discipline?: string | null;
  /** Дисциплина словами; null, если не размечена. */
  discipline_label?: string | null;
};

export type IncidentPage = {
  items: Incident[];
  total: number;
};

export type IncidentLog = {
  id: string;
  incident_id: string;
  author_id: string | null;
  stage: string;
  status: string;
  message: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export const incidentsApi = {
  list: async (params?: {
    company_id?: string;
    site_id?: string;
    status_filter?: string;
    incident_type?: string;
    discipline?: string;
    limit?: number;
    offset?: number;
  }) => {
    const { data } = await apiClient.get<IncidentPage>("/incidents", {
      params,
    });
    return data;
  },
  listLogs: async (incidentId: string) => {
    const { data } = await apiClient.get<IncidentLog[]>(
      `/incidents/${incidentId}/logs`,
    );
    return data;
  },
  create: async (payload: {
    title: string;
    description?: string;
    incident_type: string;
    occurred_at: string;
    company_id: string;
    site_id?: string;
    severity: string;
    discipline?: string | null;
  }) => {
    const { data } = await apiClient.post<Incident>("/incidents", payload);
    return data;
  },
};
