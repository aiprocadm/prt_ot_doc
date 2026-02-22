import { apiClient } from "@/api/client";

export type SignatureRequest = { id: string; status: string; provider: string };

export const signApi = {
  list: async (status?: string) => {
    const { data } = await apiClient.get<{ items: SignatureRequest[] }>("/v1/sign/requests", { params: { status } });
    return data.items;
  },
};
