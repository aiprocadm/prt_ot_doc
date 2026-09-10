import { apiClient } from "@/api/client";
import type {
  NpaActCreateDto,
  NpaDto,
  NpaRevisionCreateDto,
  NpaRevisionDto,
} from "@/types/dto/npa";

export const npaApi = {
  getDetail: async <T>(id: string): Promise<T> => {
    const { data } = await apiClient.get<T>(`/npa/${id}`);
    return data;
  },
  createImpactTasks: async (id: string): Promise<void> => {
    await apiClient.post(`/npa/${id}/impact/tasks`);
  },
  /** Срез-141: единственная точка входа в общий реестр (владелец платформы). */
  createAct: async (payload: NpaActCreateDto): Promise<NpaDto> => {
    const { data } = await apiClient.post<NpaDto>("/npa", payload);
    return data;
  },
  createRevision: async (
    actId: string,
    payload: NpaRevisionCreateDto,
  ): Promise<NpaRevisionDto> => {
    const { data } = await apiClient.post<NpaRevisionDto>(
      `/npa/${actId}/revisions`,
      payload,
    );
    return data;
  },
};
