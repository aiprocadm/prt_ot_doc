import { apiClient } from "@/api/client";
import type { DashboardOperationalSnapshotDto } from "@/types/dto/dashboard";

export const dashboardApi = {
  async getOperationalSnapshot(): Promise<DashboardOperationalSnapshotDto> {
    const { data } = await apiClient.get<DashboardOperationalSnapshotDto>(
      "/dashboard/operational",
    );
    return data;
  },
};
