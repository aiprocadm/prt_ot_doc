import { apiClient } from "@/api/client";

export type PwaConflictItem = {
  id: string;
  entity_type: string;
  conflict_code: string;
  status: string;
  failed_at?: string | null;
};

type PwaBootstrapDto = {
  offline_queue?: {
    conflict_count?: number;
    failed_conflicts?: PwaConflictItem[];
  };
};

export const pwaSyncApi = {
  async getBootstrap() {
    const response = await apiClient.get<PwaBootstrapDto>("/pwa/bootstrap");
    return response.data;
  },
  async resolveConflict(batchId: string, strategy: "server_wins" | "client_retry") {
    const response = await apiClient.post(`/pwa/sync/conflicts/${batchId}/resolve`, { strategy });
    return response.data;
  }
};
