// Вид арендатора = его уровень в иерархии продажи платформы (ТЗ Доп. №1
// разд. 52.1). `reseller` — партнёр, который ведёт своих клиентов под своим
// брендом. Список обязан совпадать с `TenantKind` в
// backend/app/schemas/tenant.py; расхождение стережёт
// backend/tests/test_tenant_kinds_single_source.py — разъедься они, форма
// отправила бы вид, который сервер не принимает.
export const TENANT_KINDS = ["customer", "branch", "contractor", "reseller"] as const;

export type TenantKind = (typeof TENANT_KINDS)[number];

export interface TenantDto {
  id: string;
  name: string;
  slug: string;
  code?: string | null;
  contact_email: string;
  is_active: boolean;
  parent_id?: string | null;
  kind?: TenantKind | null;
  schema_name?: string | null;
}

export interface TenantQuotaDto {
  tenant_id: string;
  max_parallel_jobs: number;
  max_doc_generations_per_month: number;
  max_storage_mb: number;
  monthly_edo_outgoing: number;
  enforce_billing_gate: boolean;
}

export interface TenantFeatureDto {
  code: string;
  title: string;
  on: boolean;
}

export interface TenantFleetItem {
  tenant: TenantDto;
  quotas?: TenantQuotaDto | null;
  /** Derived tier code ("free" | "pro" | "enterprise"), or null for a custom set. */
  plan?: string | null;
  features: TenantFeatureDto[];
}

/** Уровень смотрящего на кабинет арендаторов (ТЗ Доп. №1 разд. 52.1). */
export type FleetViewerLevel = "platform" | "reseller";

export interface TenantFleetPage {
  items: TenantFleetItem[];
  total: number;
  managing_tenant_slug: string;
  viewer_level: FleetViewerLevel;
  /** Приходит С СЕРВЕРА. Вычислять права на фронте — значит завести вторую правду. */
  can_manage_commercials: boolean;
}

export interface FeatureCatalogEntry {
  code: string;
  title: string;
}

export interface SubscriptionPlanDto {
  code: string;
  title: string;
  feature_codes: string[];
  quotas: Record<string, number>;
}

export interface PlanCatalog {
  plans: SubscriptionPlanDto[];
  features: FeatureCatalogEntry[];
}

/** Своя строка «сколько можно и сколько занято» (BIZ-52 срез-15, разд. 52.4). */
export interface OwnLimitLine {
  code: string;
  title: string;
  unit: string;
  /** `null` — предела нет. */
  limit: number | null;
  /** `null` — расход не считается. Это не то же, что ноль. */
  used: number | null;
  remaining: number | null;
  exhausted: boolean;
}

export interface OwnLimitsReport {
  period: string;
  tenant_slug: string;
  items: OwnLimitLine[];
}

/** Расход одного клиента за месяц (BIZ-52 срез-13, разд. 52.4). */
export interface TenantUsageRow {
  tenant_id: string;
  slug: string;
  name: string;
  doc_generations: number;
  /** Занятое хранилище в байтах — состояние, а не расход за период. */
  storage_bytes: number;
  active_workers: number;
}

export interface FleetUsageReport {
  period: string;
  items: TenantUsageRow[];
  total_doc_generations: number;
  total_storage_bytes: number;
  total_active_workers: number;
  /** Метрики, которых в отчёте нет, с причиной. Показывать обязательно:
   *  иначе отсутствие ЭДО читается как «им не пользуются». */
  not_measured: string[];
}

/** Отрасль клиента (BIZ-52 срез-12, разд. 52.3): от неё зависит наполнение
 *  справочников нового арендатора. */
export interface IndustryDto {
  code: string;
  title: string;
}

export interface IndustryList {
  items: IndustryDto[];
}

export interface TenantProvisionRequest {
  slug: string;
  name: string;
  owner_email: string;
  owner_password: string;
  kind: TenantKind;
  demo_data: boolean;
  /** Пусто — общий набор, как было до появления отраслей. */
  industry?: string;
}

export interface TenantProvisionResult {
  tenant: TenantDto;
  created: string[];
  reused: string[];
  warnings: string[];
}

export interface TenantQuotaPatch {
  max_parallel_jobs?: number;
  max_doc_generations_per_month?: number;
  max_storage_mb?: number;
  monthly_edo_outgoing?: number;
  enforce_billing_gate?: boolean;
}
