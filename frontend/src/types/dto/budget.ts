// DTO mirrors of backend/app/schemas/budget.py (§12.4 срез-1/срез-2, budget feature flag).

export type BudgetDomain = "training" | "medical" | "events";

/** overview дополнительно возвращает read-only "ppe" псевдо-домен */
export type BudgetOverviewDomainCode = BudgetDomain | "ppe";

export type BreakdownDimension =
  | "article"
  | "domain"
  | "company"
  | "branch"
  | "site";

export interface SafetyBudgetDto {
  id: string;
  name: string;
  domain: BudgetDomain;
  period_start: string;
  period_end: string;
  planned_amount: number;
  notes: string | null;
}

export interface SafetyBudgetPageDto {
  items: SafetyBudgetDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface BudgetArticleActualDto {
  article_id: string | null;
  /** "— без статьи" для NULL article_id */
  article_name: string;
  amount: number;
}

export interface SafetyBudgetDetailDto extends SafetyBudgetDto {
  actual_total: number;
  /** planned - actual; отрицательный = перерасход */
  remaining: number;
  expense_count: number;
  by_article: BudgetArticleActualDto[];
}

export interface SafetyBudgetCreateInput {
  name: string;
  domain: BudgetDomain;
  period_start: string;
  period_end: string;
  planned_amount: number;
  notes?: string | null;
}

export interface SafetyBudgetUpdateInput {
  name?: string;
  period_start?: string;
  period_end?: string;
  planned_amount?: number;
  notes?: string | null;
}

export interface BudgetArticleDto {
  id: string;
  code: string;
  name: string;
  /** NULL = универсальная статья (не привязана к домену) */
  domain: BudgetDomain | null;
  is_active: boolean;
}

export interface BudgetArticlePageDto {
  items: BudgetArticleDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface BudgetArticleCreateInput {
  code: string;
  name: string;
  domain?: BudgetDomain | null;
  is_active?: boolean;
}

export interface BudgetArticleUpdateInput {
  name?: string;
  domain?: BudgetDomain | null;
  is_active?: boolean;
  // code иммутабелен (ключ уникальности/сида)
}

export interface BudgetSeedResultDto {
  created: number;
  skipped: number;
}

export interface BudgetExpenseDto {
  id: string;
  domain: BudgetDomain;
  article_id: string | null;
  /** outerjoin в сервисе; null если article_id === null */
  article_name: string | null;
  title: string;
  occurred_on: string;
  amount: number;
  company_id: string | null;
  branch_id: string | null;
  site_id: string | null;
  entity_type: string | null;
  entity_id: string | null;
  notes: string | null;
}

export interface BudgetExpensePageDto {
  items: BudgetExpenseDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface BudgetExpenseCreateInput {
  domain: BudgetDomain;
  article_id?: string | null;
  title: string;
  occurred_on: string;
  amount: number;
  company_id?: string | null;
  branch_id?: string | null;
  site_id?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  notes?: string | null;
}

export interface BudgetExpenseUpdateInput {
  article_id?: string | null;
  title?: string;
  occurred_on?: string;
  amount?: number;
  company_id?: string | null;
  branch_id?: string | null;
  site_id?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  notes?: string | null;
  // domain иммутабелен (перенос расхода между доменами = удалить+создать)
}

export interface BudgetOverviewBudgetRowDto {
  id: string;
  name: string;
  period_start: string;
  period_end: string;
  planned_amount: number;
  actual_own_period: number;
  remaining: number;
}

export interface BudgetOverviewDomainDto {
  domain: BudgetOverviewDomainCode;
  /** True только для ppe */
  read_only: boolean;
  planned: number;
  actual: number;
  remaining: number;
  /** только ppe */
  warning_unpriced_receipts?: number | null;
  budgets: BudgetOverviewBudgetRowDto[];
}

export interface BudgetOverviewDto {
  generated_at: string;
  date_from: string;
  date_to: string;
  domains: BudgetOverviewDomainDto[];
}

export interface BudgetBreakdownItemDto {
  /** "" = None-bucket «— без привязки»/«— без статьи» */
  id: string;
  name: string;
  amount: number;
}

export interface BudgetBreakdownDto {
  dimension: BreakdownDimension;
  date_from: string;
  date_to: string;
  /** строк ДО cap 200 */
  total: number;
  items: BudgetBreakdownItemDto[];
}

/** FSM: draft -> submitted -> approved -> paid; submitted -> rejected. rejected/paid терминальны. */
export type BudgetReimbursementStatus =
  | "draft"
  | "submitted"
  | "approved"
  | "rejected"
  | "paid";

export interface BudgetReimbursementDto {
  id: string;
  title: string;
  status: BudgetReimbursementStatus;
  period_start: string;
  period_end: string;
  requested_amount: number;
  /** заполняется на approve; по умолчанию = requested_amount */
  approved_amount: number | null;
  /** внешний номер заявки в СФР */
  reference: string | null;
  company_id: string | null;
  /** обязательна при reject */
  decision_reason: string | null;
  submitted_at: string | null;
  decided_at: string | null;
  paid_at: string | null;
  notes: string | null;
  item_count: number;
  /** сумма связанных расходов (может расходиться с requested_amount) */
  items_amount: number;
}

export interface BudgetReimbursementItemDto {
  expense_id: string;
  title: string;
  domain: BudgetDomain;
  occurred_on: string;
  amount: number;
}

export interface BudgetReimbursementDetailDto extends BudgetReimbursementDto {
  items: BudgetReimbursementItemDto[];
}

export interface BudgetReimbursementPageDto {
  items: BudgetReimbursementDto[];
  total: number;
  limit: number;
  offset: number;
}

export interface BudgetReimbursementCreateInput {
  title: string;
  period_start: string;
  period_end: string;
  requested_amount: number;
  reference?: string | null;
  company_id?: string | null;
  notes?: string | null;
  // status не передаётся: заявка всегда создаётся в draft
}

export interface BudgetReimbursementUpdateInput {
  title?: string;
  period_start?: string;
  period_end?: string;
  requested_amount?: number;
  reference?: string | null;
  company_id?: string | null;
  notes?: string | null;
  // редактировать можно только draft (иначе 409); статус меняется только через действия FSM
}
