export type DashboardTrainingStatus = "ok" | "warning" | "critical";

export interface DashboardTrainingSummaryDto {
  total: number;
  overdue: number;
  due_soon: number;
  status: DashboardTrainingStatus;
}

export interface DashboardSummaryDto {
  overdue_tasks: number;
  critical_obligations: number;
  incidents_open: number;
  risks_total: number;
  training: DashboardTrainingSummaryDto;
  generated_at: string;
}
