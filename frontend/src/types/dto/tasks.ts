import type { BaseEntityDto } from "./common";

export type TaskStatus = "queued" | "in_progress" | "completed" | "failed" | "cancelled";

export interface TaskDto extends BaseEntityDto {
  kind: string;
  status: TaskStatus;
  progress: number;
  payload?: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: string | null;
}

export interface TaskFiltersDto {
  status?: TaskStatus;
  kind?: string;
}
