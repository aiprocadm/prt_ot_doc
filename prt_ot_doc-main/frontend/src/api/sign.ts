import { apiClient } from "@/api/client";

export type SignatureRequest = { id: string; status: string; provider: string };

export const signApi = {
  list: async (status?: string) => {
    const { data } = await apiClient.get<{ items: SignatureRequest[] }>("/sign/requests", { params: { status } });
    return data.items;
  },
  create: async (payload: {
    entity_type: "document" | "pack";
    entity_id: string;
    signature_type: "kep" | "unep" | "mchd";
    provider_code?: string;
    options?: Record<string, unknown>;
    approval_instance_id?: string;
  }) => {
    const { data } = await apiClient.post("/sign/requests", payload);
    return data;
  },
  refresh: async (id: string) => {
    const { data } = await apiClient.post(`/sign/requests/${id}/refresh-status`);
    return data;
  },
  verify: async (id: string) => {
    const { data } = await apiClient.post(`/sign/requests/${id}/verify`);
    return data;
  },
};
