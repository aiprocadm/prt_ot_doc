import { apiClient } from "@/api/client";

export const calendarApi = {
  getEvents: async <T>(source?: string): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>("/notifications/calendar/events", {
      params: source && source !== "all" ? { source } : undefined
    });
    return data;
  }
};

