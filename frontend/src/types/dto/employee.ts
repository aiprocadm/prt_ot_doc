// Mirrors backend/app/schemas/employee.py (vNext-EMP-01 / Phase 3.2).
// Read-only aggregate that joins personal + roles + training + medicals
// + ppe + permits + incidents + audit for the Unified Employee Card.

export type EmployeeEmploymentStatus =
  | "active"
  | "on_leave"
  | "suspended"
  | "terminated";

export type EmployeeTrainingStatus =
  | "scheduled"
  | "in_progress"
  | "completed"
  | "failed";

export type EmployeePermitStatus = "active" | "expired" | "revoked";

export type EmployeePPEIssueStatus = "issued" | "returned" | "lost";

export type EmployeeIncidentSeverity = "low" | "medium" | "high";

export type EmployeeIncidentType =
  | "accident"
  | "microtrauma"
  | "near_miss"
  | "unsafe_condition";

export type EmployeeIncidentStatus =
  | "reported"
  | "investigating"
  | "corrective_actions"
  | "closed"
  | "cancelled";

export type EmployeeIncidentPersonRole = "victim" | "witness" | "participant";

export type EmployeeDocumentStatus =
  | "draft"
  | "generated"
  | "review"
  | "approved"
  | "signed"
  | "archived"
  | "revoked";

export interface EmployeePersonalDto {
  id: string;
  company_id: string;
  company_name?: string | null;
  position_id?: string | null;
  position_name?: string | null;
  workplace_id?: string | null;
  workplace_name?: string | null;
  first_name: string;
  last_name: string;
  middle_name?: string | null;
  fio: string;
  birth_date?: string | null;
  email?: string | null;
  phone?: string | null;
  personnel_number?: string | null;
  hired_at?: string | null;
  snils?: string | null;
  passport?: string | null;
  employment_status: EmployeeEmploymentStatus | string;
  working_conditions_class?: string | null;
  hazardous_factors: string[];
  qualifications: Array<Record<string, unknown>>;
  current_ppe: Array<Record<string, unknown>>;
}

export interface EmployeeUserAccountDto {
  user_id: string;
  email: string;
  role: string;
  is_active: boolean;
  last_login_at?: string | null;
  additional_roles: string[];
}

export interface EmployeeRolesAndAssignmentsDto {
  company_id: string;
  company_name?: string | null;
  position_id?: string | null;
  position_name?: string | null;
  workplace_id?: string | null;
  workplace_name?: string | null;
  employment_status: EmployeeEmploymentStatus | string;
  user_account?: EmployeeUserAccountDto | null;
}

export interface EmployeeTrainingItemDto {
  id: string;
  course_id?: string | null;
  course_title?: string | null;
  plan_id?: string | null;
  status: EmployeeTrainingStatus | string;
  started_at?: string | null;
  completed_at?: string | null;
  score?: number | null;
}

export interface EmployeeTrainingCertificateDto {
  id: string;
  code?: string | null;
  course_id?: string | null;
  course_title?: string | null;
  issued_at: string;
  valid_until?: string | null;
  status?: string | null;
}

/**
 * Стажировка человека — та же запись, что в общем реестре `/internships`.
 * `completed_short` — недобор: завершена, а смен меньше плана. Это факт
 * расхождения плана и факта, а не вердикт о допуске к работе.
 */
export interface EmployeeInternshipItemDto {
  id: string;
  subject?: string | null;
  discipline?: string | null;
  /** Дисциплина словами; null — не размечена. */
  discipline_label?: string | null;
  /** null — наставник НЕ НАЗНАЧЕН, а не «неизвестен». */
  mentor_name?: string | null;
  planned_shifts: number;
  completed_shifts: number;
  completed_short: boolean;
  started_on?: string | null;
  finished_on?: string | null;
  status: string;
  status_label: string;
}

export interface EmployeeTrainingSectionDto {
  sessions_count: number;
  certificates_count: number;
  /** Стажировки — с среза-45; старые ответы могут прийти без них. */
  internships_count?: number;
  sessions: EmployeeTrainingItemDto[];
  certificates: EmployeeTrainingCertificateDto[];
  internships?: EmployeeInternshipItemDto[];
}

export interface EmployeeMedicalItemDto {
  id: string;
  exam_type: string;
  exam_date: string;
  valid_until: string;
  conclusion?: string | null;
  is_expired: boolean;
}

export interface EmployeeMedicalSectionDto {
  count: number;
  expired_count: number;
  items: EmployeeMedicalItemDto[];
}

export interface EmployeePPEIssueItemDto {
  id: string;
  item_id?: string | null;
  item_name: string;
  quantity: number;
  issued_at: string;
  expires_at?: string | null;
  returned_at?: string | null;
  status: EmployeePPEIssueStatus | string;
  is_expired: boolean;
}

export interface EmployeePPESectionDto {
  count: number;
  active_count: number;
  expired_count: number;
  items: EmployeePPEIssueItemDto[];
}

export interface EmployeePermitItemDto {
  id: string;
  permit_type: string;
  issued_at: string;
  valid_until?: string | null;
  status: EmployeePermitStatus | string;
  position_id?: string | null;
  is_expired: boolean;
}

export interface EmployeePermitsSectionDto {
  count: number;
  active_count: number;
  expired_count: number;
  items: EmployeePermitItemDto[];
}

export interface EmployeeIncidentItemDto {
  id: string;
  title: string;
  incident_type: EmployeeIncidentType | string;
  severity: EmployeeIncidentSeverity | string;
  status: EmployeeIncidentStatus | string;
  occurred_at: string;
  role: EmployeeIncidentPersonRole | string;
}

export interface EmployeeIncidentsSectionDto {
  count: number;
  open_count: number;
  items: EmployeeIncidentItemDto[];
}

export interface EmployeeAuditItemDto {
  id: string;
  when: string;
  action: string;
  actor_email?: string | null;
  correlation_id?: string | null;
  changed_fields: Record<string, unknown>;
}

export interface EmployeeAuditSectionDto {
  count: number;
  items: EmployeeAuditItemDto[];
}

export interface EmployeeDocumentItemDto {
  id: string;
  template_id?: string | null;
  template_name?: string | null;
  status: EmployeeDocumentStatus | string;
  is_signed: boolean;
  created_at: string;
}

export interface EmployeeDocumentsSectionDto {
  count: number;
  signed_count: number;
  items: EmployeeDocumentItemDto[];
}

export interface EmployeeBriefingItemDto {
  id: string;
  briefing_template_id?: string | null;
  briefing_template_title?: string | null;
  briefing_type: string;
  briefing_date: string;
  valid_until?: string | null;
  status: string;
  is_expired: boolean;
}

export interface EmployeeBriefingsSectionDto {
  count: number;
  expired_count: number;
  items: EmployeeBriefingItemDto[];
}

export interface EmployeeComplianceDeadlineItemDto {
  id: string;
  entity_type: string;
  entity_id: string;
  due_at: string;
  status: string;
  reminder_policy?: string | null;
  is_overdue: boolean;
}

export interface EmployeeComplianceDeadlinesSectionDto {
  count: number;
  overdue_count: number;
  upcoming_count: number;
  items: EmployeeComplianceDeadlineItemDto[];
}

export interface EmployeeCardDto {
  person_id: string;
  tenant_id: string;
  generated_at: string;
  personal: EmployeePersonalDto;
  roles_and_assignments: EmployeeRolesAndAssignmentsDto;
  training: EmployeeTrainingSectionDto;
  medicals: EmployeeMedicalSectionDto;
  ppe: EmployeePPESectionDto;
  permits: EmployeePermitsSectionDto;
  incidents: EmployeeIncidentsSectionDto;
  documents: EmployeeDocumentsSectionDto;
  briefings: EmployeeBriefingsSectionDto;
  compliance_deadlines: EmployeeComplianceDeadlinesSectionDto;
  audit: EmployeeAuditSectionDto;
}
