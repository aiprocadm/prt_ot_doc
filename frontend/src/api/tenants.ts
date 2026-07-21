import { apiClient } from "@/api/client";
import type { ApiError } from "@/types/dto/common";
import type {
  PlanCatalog,
  TenantDto,
  TenantFleetItem,
  TenantFleetPage,
  TenantProvisionRequest,
  TenantProvisionResult,
  TenantQuotaDto,
  TenantQuotaPatch
} from "@/types/dto/tenants";

const BASE = "/platform/tenants";

/** The backend answers 403 when the current tenant is not the managing one. */
export const isNotManagingTenantError = (error: unknown): boolean => {
  const e = error as Partial<ApiError> | null;
  return Boolean(e && e.status === 403);
};

export const tenantsApi = {
  async list(params: { limit?: number; offset?: number } = {}): Promise<TenantFleetPage> {
    const { data } = await apiClient.get<TenantFleetPage>(BASE, {
      params: { limit: 200, offset: 0, ...params }
    });
    return data;
  },
  async provision(payload: TenantProvisionRequest): Promise<TenantProvisionResult> {
    return (await apiClient.post<TenantProvisionResult>(BASE, payload)).data;
  },
  async setStatus(id: string, isActive: boolean): Promise<TenantDto> {
    return (await apiClient.patch<TenantDto>(`${BASE}/${id}/status`, { is_active: isActive })).data;
  },
  async updateQuotas(id: string, payload: TenantQuotaPatch): Promise<TenantQuotaDto> {
    return (await apiClient.patch<TenantQuotaDto>(`${BASE}/${id}/quotas`, payload)).data;
  },
  async plans(): Promise<PlanCatalog> {
    return (await apiClient.get<PlanCatalog>(`${BASE}/plans`)).data;
  },
  async setPlan(id: string, plan: string): Promise<TenantFleetItem> {
    return (await apiClient.patch<TenantFleetItem>(`${BASE}/${id}/plan`, { plan })).data;
  }
};
