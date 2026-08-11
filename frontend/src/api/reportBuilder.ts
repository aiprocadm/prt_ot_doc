import { apiClient } from "@/api/client";
import { downloadBlob } from "@/utils/download";
import type {
  ReportConfigDto,
  ReportDatasetDto,
  ReportDefinitionDto,
  ReportExportFormat,
  ReportExportJobDto,
  ReportPreviewDto
} from "@/types/dto/reportBuilder";

export const reportBuilderApi = {
  listDatasets: async (): Promise<{ items: ReportDatasetDto[]; total: number }> => {
    const { data } = await apiClient.get<{ items: ReportDatasetDto[]; total: number }>(
      "/report-builder/datasets"
    );
    return data;
  },
  listDefinitions: async (): Promise<{ items: ReportDefinitionDto[]; total: number }> => {
    const { data } = await apiClient.get<{ items: ReportDefinitionDto[]; total: number }>(
      "/report-builder/definitions"
    );
    return data;
  },
  createDefinition: async (payload: {
    name: string;
    description?: string | null;
    dataset_code: string;
    config_json: ReportConfigDto;
  }): Promise<ReportDefinitionDto> => {
    const { data } = await apiClient.post<ReportDefinitionDto>(
      "/report-builder/definitions",
      payload
    );
    return data;
  },
  updateDefinition: async (
    id: string,
    payload: Partial<{
      name: string;
      description: string | null;
      dataset_code: string;
      config_json: ReportConfigDto;
    }>
  ): Promise<ReportDefinitionDto> => {
    const { data } = await apiClient.patch<ReportDefinitionDto>(
      `/report-builder/definitions/${id}`,
      payload
    );
    return data;
  },
  deleteDefinition: async (id: string): Promise<void> => {
    await apiClient.delete(`/report-builder/definitions/${id}`);
  },
  preview: async (payload: {
    dataset_code: string;
    config_json: ReportConfigDto;
  }): Promise<ReportPreviewDto> => {
    const { data } = await apiClient.post<ReportPreviewDto>("/report-builder/preview", payload);
    return data;
  },
  runDefinition: async (
    id: string,
    format: ReportExportFormat
  ): Promise<{ job_id: string; status: string }> => {
    const { data } = await apiClient.post<{ job_id: string; status: string }>(
      `/report-builder/definitions/${id}/run`,
      { format }
    );
    return data;
  },
  getExportJob: async (jobId: string): Promise<ReportExportJobDto> => {
    const { data } = await apiClient.get<ReportExportJobDto>(`/exports/${jobId}`);
    return data;
  },
  downloadReportExport: async (jobId: string, filename: string): Promise<void> => {
    const { data } = await apiClient.get<Blob>(`/report-builder/exports/${jobId}/download`, {
      responseType: "blob"
    });
    downloadBlob(data, filename);
  }
};
