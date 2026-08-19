import { apiClient } from "@/api/client";

export interface AttentionItem {
  item_type: string;
  id: string;
  severity: "critical" | "high" | "medium" | "low";
  title: string;
  status: string;
  due_at: string | null;
  entity_type: string | null;
  entity_id: string | null;
  reason: string;
  /** Дисциплина записи (BIZ-54-57). null у задач и у неразмеченных источников. */
  discipline?: string | null;
}

/** Строка разреза по дисциплине (разд. 57.2). */
export interface DisciplineAttention {
  code: string;
  title: string;
  /** false — «мы это не считаем», а НЕ «ноль нарушений». */
  measured: boolean;
  overdue: number;
  due_soon: number;
  reason: string | null;
}

export interface ReadinessBlocker {
  code: string;
  title: string;
  severity: "critical" | "high" | "medium";
  count: number;
  reason: string;
  entity_type: string;
  action_hint: string;
}

export interface AttentionSummary {
  overdue_tasks: number;
  due_soon_tasks: number;
  overdue_deadlines: number;
  pending_sync_batches: number;
  failed_sync_batches: number;
  readiness_blockers: number;
}

export interface WorkspaceAttentionDto {
  generated_at: string;
  summary: AttentionSummary;
  items: AttentionItem[];
  blockers: ReadinessBlocker[];
  recommendations: string[];
  /** Поля необязательные: старые ответы (и моки тестов) их не содержат. */
  disciplines?: DisciplineAttention[];
  unclassified_sources?: string[];
  /** Показаны не все записи — сработал лимит. */
  items_truncated?: boolean;
}

export interface TaskInboxItem {
  id: string;
  title: string;
  status: string;
  priority: string;
  due_at: string | null;
  assignee_id: string | null;
  entity_type: string | null;
  entity_id: string | null;
  overdue: boolean;
}

export interface WorkspaceTaskInboxDto {
  total: number;
  overdue: number;
  items: TaskInboxItem[];
}

export interface WorkspaceConfig {
  role: string;
  workspace_type: string;
  primary_modules: string[];
  dashboard_route: string;
  kpis_enabled: string[];
  quick_actions: Array<{ label: string; route: string }>;
}

export const workspaceApi = {
  getAttention: (limit = 30): Promise<WorkspaceAttentionDto> =>
    apiClient
      .get<WorkspaceAttentionDto>(`/workspace/attention?limit=${limit}`)
      .then((r) => r.data),

  getTaskInbox: (limit = 50, offset = 0): Promise<WorkspaceTaskInboxDto> =>
    apiClient
      .get<WorkspaceTaskInboxDto>(
        `/workspace/task-inbox?limit=${limit}&offset=${offset}`,
      )
      .then((r) => r.data),

  getUserWorkspaceConfig: (): Promise<WorkspaceConfig> =>
    apiClient
      .get<WorkspaceConfig>("/workspace/users/me/workspace")
      .then((r) => r.data),
};
