/**
 * Реестр требований — форма ответа `GET /compliance/requirements`
 * (backend/app/schemas/compliance_requirements.py; B.18 разд. 19.2, срез-145).
 *
 * `overdue` и `days_left` считает сервер по UTC-«сегодня»: витрина их не
 * пересчитывает, иначе вечером по Москве «сегодня» разошлось бы с сервером.
 */

export type RequirementSeverity = "low" | "medium" | "high" | "critical";
export type RequirementStatus = "active" | "fulfilled" | "retired";

export interface ComplianceEvidenceDto {
  id: string;
  requirement_id: string;
  document_id?: string | null;
  document_title?: string | null;
  note?: string | null;
  confirmed_at: string;
  confirmed_by?: string | null;
  created_at: string;
}

export interface ComplianceRequirementDto {
  id: string;
  code: string;
  title: string;
  description?: string | null;
  npa_id?: string | null;
  npa_code?: string | null;
  npa_title?: string | null;
  clause_id?: string | null;
  clause_code?: string | null;
  role_code?: string | null;
  site_id?: string | null;
  process_code?: string | null;
  owner_user_id?: string | null;
  owner_name?: string | null;
  periodicity_days?: number | null;
  next_due_at?: string | null;
  last_confirmed_at?: string | null;
  severity: RequirementSeverity;
  status: RequirementStatus;
  retired_at?: string | null;
  overdue: boolean;
  days_left?: number | null;
  evidence_count: number;
  created_at: string;
  updated_at: string;
}

export interface ComplianceRequirementDetailDto
  extends ComplianceRequirementDto {
  evidence: ComplianceEvidenceDto[];
}

export interface ComplianceRequirementListDto {
  items: ComplianceRequirementDto[];
  total: number;
  active: number;
  overdue: number;
  /** Право заводить, подтверждать и снимать с контроля (admin/owner/ot_specialist). */
  can_manage: boolean;
}

export interface ComplianceRequirementCreateDto {
  code: string;
  title: string;
  description?: string | null;
  npa_id?: string | null;
  clause_id?: string | null;
  role_code?: string | null;
  site_id?: string | null;
  process_code?: string | null;
  owner_user_id?: string | null;
  periodicity_days?: number | null;
  next_due_at?: string | null;
  severity?: RequirementSeverity;
}

export interface ComplianceEvidenceCreateDto {
  document_id?: string | null;
  note?: string | null;
  confirmed_at?: string | null;
}

export interface ComplianceRequirementFiltersDto {
  npa_id?: string;
  status?: RequirementStatus;
  overdue?: boolean;
}
