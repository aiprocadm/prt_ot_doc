/**
 * Реестр требований — форма ответа `GET /compliance/requirements`
 * (backend/app/schemas/compliance_requirements.py; B.18 разд. 19.2, срез-145).
 *
 * `overdue` и `days_left` считает сервер по UTC-«сегодня»: витрина их не
 * пересчитывает, иначе вечером по Москве «сегодня» разошлось бы с сервером.
 * Имена (`owner_name`, `site_name`, `role_label`) тоже приходят с сервера:
 * витрина ничего не знает о пользователях и площадках, кроме того, что ей
 * отдали для выбора.
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
  /** Роль словами (срез-147); код — для машин. */
  role_label?: string | null;
  site_id?: string | null;
  /** Имя площадки (срез-147): без него привязка к объекту невидима. */
  site_name?: string | null;
  process_code?: string | null;
  /** Процесс словами (срез-196). Неизвестный код возвращается как есть: у
   * требований до среза в поле лежит свободный текст. */
  process_label?: string | null;
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
  /**
   * Счётчики по ВСЕЙ выборке при текущих фильтрах, а не по выданной странице
   * (срез-195): счётчик по странице заставил бы человека сделать ложный вывод
   * «просроченных нет», увидев «просрочено: 0» над первой страницей.
   */
  total: number;
  active: number;
  overdue: number;
  /** Какая часть выдана. Длина списка этого не заменяет: пустая последняя
   * страница неотличима от «ничего не найдено». */
  limit: number;
  offset: number;
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

/** Правка (срез-147): всё, кроме кода — он естественный ключ арендатора. */
export type ComplianceRequirementUpdateDto = Omit<
  ComplianceRequirementCreateDto,
  "code"
>;

export interface ComplianceEvidenceCreateDto {
  document_id?: string | null;
  note?: string | null;
  confirmed_at?: string | null;
}

export interface ComplianceRequirementFiltersDto {
  npa_id?: string;
  status?: RequirementStatus;
  overdue?: boolean;
  /** Срез-195: реестр листается страницами (по умолчанию сервер отдаёт 50). */
  limit?: number;
  offset?: number;
}

/** Кандидат в ответственные: только то, что нужно, чтобы выбрать человека. */
export interface RequirementOwnerOptionDto {
  id: string;
  name: string;
  role: string;
  role_label: string;
}

export interface RequirementSiteOptionDto {
  id: string;
  name: string;
  /** Компания площадки: у аутсорсера «Цех №1» бывает у нескольких клиентов. */
  company_name: string;
}

export interface RequirementRoleOptionDto {
  code: string;
  label: string;
}

/** Справочники формы требования — `GET /compliance/requirements/options` (срез-147). */
export interface ComplianceRequirementOptionsDto {
  owners: RequirementOwnerOptionDto[];
  sites: RequirementSiteOptionDto[];
  roles: RequirementRoleOptionDto[];
  /** Процессы (срез-196): дисциплины ТЗ + общая охрана труда. */
  processes: RequirementRoleOptionDto[];
}
