import { apiClient } from "@/api/client";

export type EdoEnvelope = { id: string; status: string; external_id: string | null };

export const edoApi = {
  list: async (status?: string) => {
    const { data } = await apiClient.get<{ items: EdoEnvelope[] }>("/v1/edo/envelopes", { params: { status } });
    return data.items;
  },
};
