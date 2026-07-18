/**
 * Филиал (Branch) — master-data уровень между Company и Site (RC-014).
 * BranchRead возвращает только поля BranchBase + id (без таймстампов).
 */

/** Статус на бэкенде — свободный VARCHAR(32) (не PG-enum), по умолчанию "active". */
export type BranchStatus = string;

export interface BranchDto {
  id: string;
  company_id: string;
  name: string;
  code?: string;
  address?: string;
  contact_name?: string;
  contact_phone?: string;
  contact_email?: string;
  status: BranchStatus;
}

export interface BranchFiltersDto {
  company_id?: string;
}

/** Тело POST /branches (BranchCreate). */
export interface CreateBranchDto {
  company_id: string;
  name: string;
  code?: string;
  address?: string;
  contact_name?: string;
  contact_phone?: string;
  contact_email?: string;
  status?: BranchStatus;
}

/** Тело PATCH /branches/{id} (BranchUpdate — без company_id). */
export interface UpdateBranchDto {
  name?: string;
  code?: string;
  address?: string;
  contact_name?: string;
  contact_phone?: string;
  contact_email?: string;
  status?: BranchStatus;
}
