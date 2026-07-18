import { apiClient } from "@/api/client";
import type {
  AnalyticsFiltersDto,
  BreakdownDto,
  DashboardWidgetsDto,
  DirectoryItemDto,
  ExecutiveDashboardDto,
  TrendSeriesDto
} from "@/types/dto/analytics";

const clean = (filters: AnalyticsFiltersDto): Record<string, string> => {
  const params: Record<string, string> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") params[key] = value;
  }
  return params;
};

type DirectoryPage = { items?: DirectoryItemDto[]; total?: number };

export const analyticsApi = {
  getDashboard: async <T = DashboardWidgetsDto>(
    name: "executive" | "overdue" | "sla-load",
    filters: AnalyticsFiltersDto
  ): Promise<T> => {
    const { data } = await apiClient.get<T>(`/analytics/dashboard/${name}`, {
      params: clean(filters)
    });
    return data;
  },
  getExecutive: async (filters: AnalyticsFiltersDto): Promise<ExecutiveDashboardDto> => {
    const { data } = await apiClient.get<ExecutiveDashboardDto>(
      "/analytics/dashboard/executive",
      { params: clean(filters) }
    );
    return data;
  },
  getTrend: async (
    metric: "incidents" | "compliance" | "packages" | "trainings" | "inspections" | "ppe",
    period: "daily" | "weekly" | "monthly"
  ): Promise<TrendSeriesDto> => {
    const { data } = await apiClient.get<TrendSeriesDto>(`/analytics/trends/${metric}`, {
      params: { period }
    });
    return data;
  },
  getBreakdown: async (
    dimension: "company" | "site" | "contractor",
    window: Pick<AnalyticsFiltersDto, "date_from" | "date_to">
  ): Promise<BreakdownDto> => {
    const { data } = await apiClient.get<BreakdownDto>("/analytics/dashboard/breakdown", {
      params: { dimension, ...clean(window) }
    });
    return data;
  },
  getCompanies: async (): Promise<DirectoryPage> => {
    const { data } = await apiClient.get<DirectoryPage>("/companies", {
      params: { limit: 200 }
    });
    return data;
  },
  getSites: async (): Promise<DirectoryPage> => {
    const { data } = await apiClient.get<DirectoryPage>("/sites", {
      params: { limit: 200 }
    });
    return data;
  },
  getContractors: async (): Promise<DirectoryPage> => {
    const { data } = await apiClient.get<DirectoryPage>("/contractors/registry", {
      params: { limit: 200 }
    });
    return data;
  }
};
