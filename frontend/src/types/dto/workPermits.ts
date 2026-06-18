export interface WorkPermitMemberDto {
  id: string;
  person_id: string;
  role: string;
  created_at: string;
}

export interface WorkPermitDto {
  id: string;
  number: string | null;
  work_type: string;
  zone_text: string;
  site_id: string | null;
  equipment_text: string | null;
  hazards_text: string | null;
  measures_text: string | null;
  planned_start: string | null;
  planned_end: string | null;
  status: string;
  opened_at: string | null;
  closed_at: string | null;
  suspended_at: string | null;
  members: WorkPermitMemberDto[];
  subdivision_text: string | null;
  content_text: string | null;
  conditions_text: string | null;
  safety_systems: string[] | null;
  measures_before_text: string | null;
  measures_during_text: string | null;
  special_conditions_text: string | null;
  ppe_text: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkPermitPage {
  items: WorkPermitDto[];
  total: number;
}

export interface WorkPermitEventDto {
  id: string;
  event_type: string;
  at: string;
  actor_user_id: string | null;
  photo_file_id: string | null;
  note: string | null;
}

export interface ViolationDto {
  person_id: string;
  role: string;
  code: string;
  severity: string;
}

export interface ReadinessReportDto {
  ok: boolean;
  violations: ViolationDto[];
}
