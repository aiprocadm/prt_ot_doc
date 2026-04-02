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

export interface DashboardTaskInboxItemDto {
  id: string;
  title: string;
  owner_label?: string | null;
  due_at?: string | null;
  priority: string;
  status: string;
  overdue: boolean;
  entity_type?: string | null;
  entity_id?: string | null;
}

export interface DashboardDocumentInboxItemDto {
  id: string;
  title: string;
  route_label: string;
  status: string;
  risk: string;
  created_at: string;
  template_code?: string | null;
  template_version?: number | null;
}

export interface DashboardReadinessSnapshotDto {
  packages_total: number;
  open_gaps: number;
  critical_gaps: number;
  latest_target_date?: string | null;
  readiness_score: number;
  reasons: string[];
}

export interface DashboardOperationalSnapshotDto {
  tasks: DashboardTaskInboxItemDto[];
  documents: DashboardDocumentInboxItemDto[];
  readiness: DashboardReadinessSnapshotDto;
  generated_at: string;
}
