import { apiClient } from "@/api/client";

export const npaApi = {
  getDetail: async <T>(id: string): Promise<T> => {
    const { data } = await apiClient.get<T>(`/npa/${id}`);
    return data;
  },
  createImpactTasks: async (id: string): Promise<void> => {
    await apiClient.post(`/npa/${id}/impact/tasks`);
  },
};
