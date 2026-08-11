import { apiClient } from "@/api/client";

export const integrationsApi = {
  getOutbox: async <T>(): Promise<{ items: T[] }> => {
    const { data } = await apiClient.get<{ items: T[] }>("/admin/outbox");
    return data;
  },
  getOutboxEvents: async <T>(): Promise<{ items: T[] }> => {
    const { data } = await apiClient.get<{ items: T[] }>("/admin/outbox/events");
    return data;
  },
  getReadiness: async <T>(): Promise<T> => {
    const { data } = await apiClient.get<T>("/integrations/readiness");
    return data;
  },
  retryOutboxDelivery: async (id: string): Promise<void> => {
    await apiClient.post(`/admin/outbox/${id}/retry`);
  },
  retryOutboxEvent: async (id: string): Promise<void> => {
    await apiClient.post(`/admin/outbox/events/${id}/requeue`);
  }
};

