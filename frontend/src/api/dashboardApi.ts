import { apiClient } from "@/api/client";

export const dashboardApiClient = {
  getByEndpoint: async (endpoint: string): Promise<Record<string, unknown>> => {
    const { data } = await apiClient.get<Record<string, unknown>>(endpoint);
    return data;
  },
};
