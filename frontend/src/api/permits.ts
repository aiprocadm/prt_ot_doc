import { apiClient } from "@/api/client";
import type {
  PermitCreatePayload,
  PermitDto,
  PermitPage,
  PermitUpdatePayload
} from "@/types/dto/permits";

const BASE = "/permits";

export type PermitListParams = {
  person_id?: string;
  status?: string;
  expired_only?: boolean;
  limit?: number;
  offset?: number;
};

export const permitsApi = {
  async listPermits(params: PermitListParams = {}): Promise<PermitPage> {
    const { data } = await apiClient.get<PermitPage>(BASE, {
      params: { limit: 200, offset: 0, ...params }
    });
    return { items: data.items ?? [], total: data.total ?? 0 };
  },

  async countPermits(params: Omit<PermitListParams, "limit" | "offset"> = {}): Promise<number> {
    const { data } = await apiClient.get<PermitPage>(BASE, {
      params: { ...params, limit: 1, offset: 0 }
    });
    return data.total ?? 0;
  },

  async createPermit(payload: PermitCreatePayload): Promise<PermitDto> {
    const { data } = await apiClient.post<PermitDto>(BASE, payload);
    return data;
  },

  async updatePermit(id: string, payload: PermitUpdatePayload): Promise<PermitDto> {
    const { data } = await apiClient.patch<PermitDto>(`${BASE}/${id}`, payload);
    return data;
  },

  async extendPermit(id: string, validUntil: string): Promise<PermitDto> {
    const { data } = await apiClient.post<PermitDto>(`${BASE}/${id}/extend`, {
      valid_until: validUntil
    });
    return data;
  },

  async revokePermit(id: string): Promise<PermitDto> {
    const { data } = await apiClient.post<PermitDto>(`${BASE}/${id}/revoke`, {});
    return data;
  }
};
