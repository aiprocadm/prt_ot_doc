// Mirrors backend/app/schemas/calendar.py (vNext-CAL-01 / Phase 4.1).
// Read-only aggregate from /api/v1/calendar/events spanning medicals,
// PPE, permits, training, inspections, compliance deadlines, briefings
// and legacy calendar projections — normalized into a single shape.

export type CalendarSourceType =
  | "medical_exam"
  // medical_referral отдавался бэкендом с самого начала, а в этом списке его
  // не было: список написан руками, и сверять его с ALL_SOURCES было нечем.
  // Теперь сверяет тест tests/test_ecology_calendar.py.
  | "medical_referral"
  | "ppe_issue"
  | "permit"
  | "training_session"
  | "inspection"
  | "compliance_deadline"
  | "briefing_entry"
  | "calendar_event"
  // Доп. №1 разд. 55.3 «экологический календарь».
  | "ecology_permit"
  | "ecology_measurement"
  // Доп. №1 разд. 55.3 (срез-71): сроки 2-ТП, декларации НВОС и платежей.
  | "ecology_report"
  // Доп. №1 разд. 57.2 (срез-57): ЭПБ на ОПО, учения ГО, документы ТС.
  | "industrial_safety_epb"
  | "civil_defense_drill"
  | "road_safety_vehicle"
  | "road_safety_driver";

export const CALENDAR_SOURCE_TYPES: readonly CalendarSourceType[] = [
  "medical_exam",
  "medical_referral",
  "ppe_issue",
  "permit",
  "training_session",
  "inspection",
  "compliance_deadline",
  "briefing_entry",
  "calendar_event",
  "ecology_permit",
  "ecology_measurement",
  "ecology_report",
  "industrial_safety_epb",
  "civil_defense_drill",
  "road_safety_vehicle",
  "road_safety_driver",
] as const;

export type CalendarSlaBand = "overdue" | "critical" | "warning" | "ok";

export const CALENDAR_SLA_BANDS: readonly CalendarSlaBand[] = [
  "overdue",
  "critical",
  "warning",
  "ok",
] as const;

export interface CalendarEventItemDto {
  id: string;
  source_type: CalendarSourceType;
  source_id: string;
  title: string;
  starts_at: string;
  ends_at?: string | null;
  status?: string | null;
  is_overdue: boolean;
  person_id?: string | null;
  site_id?: string | null;
  company_id?: string | null;
  assigned_user_id?: string | null;
  expected_at?: string | null;
  actual_at?: string | null;
  variance_days?: number | null;
  days_to_due?: number | null;
  sla_band?: CalendarSlaBand | null;
  extra: Record<string, unknown>;
}

export interface CalendarSourceCountDto {
  source_type: CalendarSourceType;
  count: number;
  overdue_count: number;
  /** Просрочки по виду записи (например, `briefing_type`) — только у
   * источников, где дисциплина зависит от вида; у остальных `null`. */
  overdue_by_kind?: Record<string, number> | null;
}

export interface CalendarEventsResponseDto {
  generated_at: string;
  range_from?: string | null;
  range_to?: string | null;
  total: number;
  overdue_count: number;
  by_source: CalendarSourceCountDto[];
  items: CalendarEventItemDto[];
}

export interface CalendarEventsQuery {
  from_at?: string;
  to_at?: string;
  source_types?: CalendarSourceType[];
  person_id?: string;
  site_id?: string;
  include_fact?: boolean;
  include_sla?: boolean;
}

// --- Saved Smart Calendar views (vNext-CAL-01 / Phase 4.1) ---
// Mirrors backend/app/schemas/calendar_views.py
//
// `payload` snapshots the calendar URL filter state so the dropdown can
// re-apply it with one click. Adding a new toggle is additive: extend
// CalendarSavedViewPayloadDto and the backend pydantic model; no
// migration needed (the column stores opaque JSON).

export type CalendarViewKind = "day" | "week" | "month" | "year" | "list";

export type CalendarLoadDimension = "person" | "site";

export interface CalendarSavedViewPayloadDto {
  view?: CalendarViewKind | null;
  sources: CalendarSourceType[];
  person_id?: string | null;
  site_id?: string | null;
  include_fact: boolean;
  include_sla: boolean;
  sla_bands: CalendarSlaBand[];
  include_load: boolean;
  load_dim?: CalendarLoadDimension | null;
}

export interface CalendarSavedViewDto {
  id: string;
  name: string;
  payload: CalendarSavedViewPayloadDto;
  created_at: string;
  updated_at: string;
}

export interface CalendarSavedViewWriteRequest {
  name: string;
  payload: CalendarSavedViewPayloadDto;
}
