// Mirrors backend/app/schemas/calendar.py (vNext-CAL-01 / Phase 4.1).
// Read-only aggregate from /api/v1/calendar/events spanning medicals,
// PPE, permits, training, inspections, compliance deadlines, briefings
// and legacy calendar projections — normalized into a single shape.

export type CalendarSourceType =
  | "medical_exam"
  | "ppe_issue"
  | "permit"
  | "training_session"
  | "inspection"
  | "compliance_deadline"
  | "briefing_entry"
  | "calendar_event";

export const CALENDAR_SOURCE_TYPES: readonly CalendarSourceType[] = [
  "medical_exam",
  "ppe_issue",
  "permit",
  "training_session",
  "inspection",
  "compliance_deadline",
  "briefing_entry",
  "calendar_event"
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
  extra: Record<string, unknown>;
}

export interface CalendarSourceCountDto {
  source_type: CalendarSourceType;
  count: number;
  overdue_count: number;
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
}
