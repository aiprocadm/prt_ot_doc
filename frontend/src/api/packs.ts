import { apiClient } from "@/api/client";

export const packsApi = {
  getProfiles: async <T>(): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>("/package-profiles");
    return data;
  },
  createProfile: async (payload: Record<string, unknown>): Promise<void> => {
    await apiClient.post("/package-profiles", payload);
  },
  getPresets: async <T>(): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>("/package-presets");
    return data;
  },
  createPreset: async (payload: Record<string, unknown>): Promise<void> => {
    await apiClient.post("/package-presets", payload);
  },
  validatePreset: async (id: string): Promise<void> => {
    await apiClient.post(`/package-presets/${id}:validate`);
  },
  getRunItems: async <T>(id: string): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>(`/pack-runs/${id}/items`);
    return data;
  },
  getRunTimeline: async <T>(id: string): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>(`/pack-runs/${id}/timeline`);
    return data;
  },
  retryFailedRunItems: async (id: string): Promise<void> => {
    await apiClient.post(`/pack-runs/${id}:retry-failed`);
  }
};

