import type { BaseEntityDto } from "./common";

export type TemplateStatus = "draft" | "active" | "published" | "uploaded" | "linted" | "ready" | "archived" | "deprecated";

export interface TemplateScopeDto {
  type: "global" | "system" | "tenant" | "legal_entity" | "organization" | "site" | string;
  tenant_id?: string | null;
  company_id?: string | null;
  site_id?: string | null;
  label?: string | null;
  applicability?: string | null;
}

export interface TemplateVersionDto extends BaseEntityDto {
  template_id: string;
  version: number;
  status: TemplateStatus;
  sha256?: string | null;
  size_bytes?: number | null;
  file_id?: string | null;
  placeholder_index?: Record<string, unknown> | null;
  linter_report_json?: Record<string, unknown> | null;
  document_type?: string | null;
  applicability_rules?: Record<string, unknown> | null;
  output_types?: string[] | null;
  profile?: Record<string, unknown> | null;
}

export interface TemplateDto extends BaseEntityDto {
  code?: string | null;
  name: string;
  description?: string | null;
  category?: string | null;
  status?: TemplateStatus | null;
  current_version_id?: string | null;
  version: number;
  metadata_json?: Record<string, unknown> | null;
  template_type?: string | null;
  scope?: TemplateScopeDto | null;
  current_version?: TemplateVersionDto | null;
  versions?: TemplateVersionDto[];
  tags?: string[];
}

export interface UpdateTemplateDto {
  code?: string;
  name: string;
  description?: string;
  category?: string;
  status?: "draft" | "active" | "archived";
  scope?: TemplateScopeDto;
  tags?: string[];
  version_id?: string;
  template_type?: string;
}
