import { apiClient } from "@/api/client";

export type AlertSeverity = "critical" | "high" | "medium" | "low";

export type AlertCategory =
  | "overdue"
  | "blocked_approval"
  | "integration_error"
  | "high_risk"
  | "health_warning"
  | "unassigned_task"
  | "data_quality";

/** One alert bucket from GET /api/v1/operational/dashboard (backend: AlertItem). */
export type AlertItem = {
  id: string;
  category: AlertCategory;
  severity: AlertSeverity;
  title: string;
  description?: string | null;
  count: number;
  affected_entity_type?: string | null;
  affected_entity_id?: string | null;
  action_url?: string | null;
  created_at: string;
  expires_at?: string | null;
};

export type OperationalDashboardStatus = "ok" | "warning" | "critical";

/** Backend: OperationalDashboardResponse. */
export type OperationalDashboardDto = {
  tenant_id: string;
  status: OperationalDashboardStatus;
  alerts: AlertItem[];
  alert_count: Partial<Record<AlertSeverity, number>>;
  health_status?: string | null;
  timestamp: string;
};

export const operationalDashboardApi = {
  /**
   * Operational alerts aggregator. X-Tenant-Id is injected by apiClient
   * (same mechanism the health contour relies on).
   */
  getDashboard: async (): Promise<OperationalDashboardDto> => {
    const response = await apiClient.get<OperationalDashboardDto>("/operational/dashboard");
    return response.data;
  }
};
