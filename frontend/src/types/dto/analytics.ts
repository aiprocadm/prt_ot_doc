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
  /** null — метрика по этой строке НЕ считается (не ноль). */
  [metric: string]: string | number | null;
}

export type BreakdownDimension =
  | "company"
  | "site"
  | "contractor"
  | "discipline";

export interface BreakdownDto {
  dimension: BreakdownDimension;
  items: BreakdownRowDto[];
  total: number;
}

export interface DirectoryItemDto {
  id: string;
  name: string;
}

/** Строка авто-отчёта о состоянии по дисциплине (Доп. №1 разд. 57.4). */
export interface DisciplineReportRowDto {
  discipline: string;
  title: string;
  incidents_open: number;
  /** null — просрочки по этой дисциплине не считаются (не ноль). */
  overdue_items: number | null;
  total_issues: number;
  /** null — в прошлом отчёте этой дисциплины не было. */
  previous_total_issues: number | null;
  delta: number | null;
}

export interface DisciplineReportPayloadDto {
  period: { start: string; end: string };
  rows: DisciplineReportRowDto[];
  unmarked_incidents: number;
  totals: {
    incidents_open: number;
    overdue_items: number;
    total_issues: number;
    previous_total_issues: number | null;
    delta: number | null;
  };
  previous_period_end: string | null;
  worst: { discipline: string; title: string } | null;
  actions: string[];
}

/** Снимок состояния по дисциплинам на дату — запись, а не пересчёт. */
export interface DisciplineReportDto {
  id: string;
  period_start: string;
  period_end: string;
  total_issues: number;
  summary: string;
  payload: DisciplineReportPayloadDto;
}

export interface DisciplineReportPageDto {
  items: DisciplineReportDto[];
  total: number;
}

export interface DisciplineReportRunDto {
  created: boolean;
  report: DisciplineReportDto;
  /** Сколько уведомлений ушло получателям (срез-51); у повторного запуска 0. */
  notified: number;
  summary: string;
}
