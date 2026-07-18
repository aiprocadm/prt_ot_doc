import { apiClient } from "@/api/client";
import type { DataQualityReportDto } from "@/types/dto/dataQuality";

export const dataQualityApi = {
  async getReport(): Promise<DataQualityReportDto> {
    const { data } = await apiClient.get<DataQualityReportDto>("/data-quality/report");
    return data;
  }
};
