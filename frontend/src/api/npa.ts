import { apiClient } from "@/api/client";
import type {
  NpaActCreateDto,
  NpaBindingCreateDto,
  NpaBindingOptionsDto,
  NpaBindingDto,
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
  /** Срез-142: связи акта с документами арендатора — их читает оценка влияния. */
  /** Срез-197: справочники области действия связи — роли и площадки. */
  bindingOptions: async (): Promise<NpaBindingOptionsDto> => {
    const { data } = await apiClient.get<NpaBindingOptionsDto>(
      "/npa/binding-options",
    );
    return data;
  },
  createBinding: async (
    actId: string,
    payload: NpaBindingCreateDto,
  ): Promise<NpaBindingDto> => {
    const { data } = await apiClient.post<NpaBindingDto>(
      `/npa/${actId}/bindings`,
      payload,
    );
    return data;
  },
  deleteBinding: async (actId: string, bindingId: string): Promise<void> => {
    await apiClient.delete(`/npa/${actId}/bindings/${bindingId}`);
  },
  /** Срез-144: «Пересмотрено» — связь сверена по действующей редакции акта. */
  reviewBinding: async (
    actId: string,
    bindingId: string,
  ): Promise<NpaBindingDto> => {
    const { data } = await apiClient.post<NpaBindingDto>(
      `/npa/${actId}/bindings/${bindingId}/review`,
    );
    return data;
  },
};
