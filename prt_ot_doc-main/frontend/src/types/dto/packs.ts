import type { BaseEntityDto } from "./common";
import type { CompanyDto } from "./companies";

export type PackPreset =
  | "site_entry"
  | "incident_response"
  | "fire_safety"
  | "environmental"
  | "custom";

export interface PackDto extends BaseEntityDto {
  name: string;
  preset: PackPreset;
  description?: string;
  company?: CompanyDto;
  status: "draft" | "processing" | "ready" | "failed";
  started_at?: string;
  completed_at?: string;
  task_id?: string;
}

export interface PackGenerationPayload {
  company_id: string;
  preset: PackPreset;
  parameters: Record<string, unknown>;
}
