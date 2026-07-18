import { apiClient } from "@/api/client";

export type NotificationsQuery = {
  status?: string;
  channel?: string;
  priority?: string;
  type?: string;
};

export const notificationsApi = {
  list: async <T>(params: NotificationsQuery): Promise<{ items: T[]; unread_count: number }> => {
    const { data } = await apiClient.get<{ items: T[]; unread_count: number }>("/notifications", { params });
    return data;
  },
  getMySettings: async <T>(): Promise<T> => {
    const { data } = await apiClient.get<T>("/notifications/settings/me");
    return data;
  },
  saveMySettings: async <T extends Record<string, unknown>>(payload: T): Promise<void> => {
    await apiClient.put("/notifications/settings/me", payload);
  },
  listTemplates: async <T>(): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>("/notifications/templates");
    return data;
  },
  markRead: async (ids: string[]): Promise<void> => {
    await apiClient.post("/notifications/mark-read", { ids });
  }
};

