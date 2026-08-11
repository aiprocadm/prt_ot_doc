import { apiClient } from "@/api/client";

export type KpiQuery = {
  date_from: string;
  date_to: string;
};

export const reportsApi = {
  getExports: async <T>(): Promise<{ total: number; items?: T[] }> => {
    const { data } = await apiClient.get<{ total: number; items?: T[] }>("/exports");
    return data;
  },
  getExportSchedules: async <T>(): Promise<{ total: number; items?: T[] }> => {
    const { data } = await apiClient.get<{ total: number; items?: T[] }>("/exports/schedules");
    return data;
  },
  getExportKpis: async <T>(): Promise<{ total: number; items?: T[] }> => {
    const { data } = await apiClient.get<{ total: number; items?: T[] }>("/exports/kpis");
    return data;
  },
  getDatasets: async <T>(): Promise<{ total: number; items?: T[] }> => {
    const { data } = await apiClient.get<{ total: number; items?: T[] }>("/exports/datasets");
    return data;
  },
  getKpi: async <T>(query: KpiQuery): Promise<T> => {
    const { data } = await apiClient.get<T>("/reports/kpi", { params: query });
    return data;
  },
  queueExport: async (format: "xlsx" | "pdf", dateFrom: string, dateTo: string): Promise<{ id: string; status: string }> => {
    const { data } = await apiClient.post<{ id: string; status: string }>(
      "/exports",
      {
        export_type: `reports:${format}`,
        scope_json: { page: "reports", format },
        filters_json: { date_from: dateFrom, date_to: dateTo, format, anonymized: false }
      },
      {
        headers: { "Idempotency-Key": `reports:${format}:${dateFrom}:${dateTo}` }
      }
    );
    return data;
  }
};

