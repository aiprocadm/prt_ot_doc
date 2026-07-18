export interface AnalyticsFiltersDto {
  company_id?: string;
  site_id?: string;
  contractor_id?: string;
  date_from?: string;
  date_to?: string;
}

export interface DashboardWidgetsDto {
  name?: string;
  widgets: Record<string, number>;
}

export interface ExecutiveDashboardDto {
  snapshot_date: string;
  widgets: Record<string, unknown>;
  dashboard: DashboardWidgetsDto;
}

export interface TrendPointDto {
  date: string;
  value: number;
}

export interface TrendSeriesDto {
  metric: string;
  period: "daily" | "weekly" | "monthly";
  series: TrendPointDto[];
}

export interface BreakdownRowDto {
  id: string;
  name: string;
  total_issues: number;
  [metric: string]: string | number;
}

export interface BreakdownDto {
  dimension: "company" | "site" | "contractor";
  items: BreakdownRowDto[];
  total: number;
}

export interface DirectoryItemDto {
  id: string;
  name: string;
}
