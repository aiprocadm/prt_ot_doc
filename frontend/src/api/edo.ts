import { apiClient } from "@/api/client";

export type EdoEnvelope = { id: string; status: string; external_id: string | null };

export const edoApi = {
  list: async (status?: string) => {
    const { data } = await apiClient.get<{ items: EdoEnvelope[] }>("/edo/messages", { params: { status } });
    return data.items;
  },
  send: async (payload: {
    entity_type: "document" | "pack";
    entity_id: string;
    operator_code: string;
    message_type: string;
  }) => {
    const { data } = await apiClient.post("/edo/messages", payload);
    return data;
  },
  refreshStatus: async (id: string) => {
    const { data } = await apiClient.post(`/edo/messages/${id}/refresh-status`);
    return data;
  },
};
