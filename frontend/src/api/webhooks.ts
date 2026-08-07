import { apiClient } from "@/api/client";

export const webhooksApi = {
  getEndpoints: async <T>(): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>("/webhooks/endpoints");
    return data;
  },
  getDeliveries: async <T>(): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>("/webhooks/deliveries");
    return data;
  },
  createEndpoint: async (payload: Record<string, unknown>): Promise<void> => {
    await apiClient.post("/webhooks/endpoints", payload);
  },
  testEndpoint: async (id: string): Promise<void> => {
    await apiClient.post(`/webhooks/endpoints/${id}:test`);
  },
};
