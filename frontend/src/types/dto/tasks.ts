import type { BaseEntityDto } from "./common";

export type TaskStatus = "open" | "in_progress" | "done" | "cancelled";
export type TaskPriority = "low" | "medium" | "high" | "critical";

export interface TaskDto extends BaseEntityDto {
  title: string;
  description?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  due_at?: string | null;
  status: TaskStatus;
  assignee_id?: string | null;
  created_by?: string | null;
  priority: TaskPriority;
  next_remind_at?: string | null;
  reminder_channel?: string | null;
  completed_at?: string | null;
  overdue?: boolean;
}

export interface TaskFiltersDto {
  status?: TaskStatus;
  overdue?: boolean;
  assignee?: string;
}
