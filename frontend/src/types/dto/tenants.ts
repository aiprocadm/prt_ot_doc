export type TenantKind = "customer" | "branch" | "contractor";

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

export interface TenantFleetItem {
  tenant: TenantDto;
  quotas?: TenantQuotaDto | null;
}

export interface TenantFleetPage {
  items: TenantFleetItem[];
  total: number;
  managing_tenant_slug: string;
}

export interface TenantProvisionRequest {
  slug: string;
  name: string;
  owner_email: string;
  owner_password: string;
  kind: TenantKind;
  demo_data: boolean;
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
