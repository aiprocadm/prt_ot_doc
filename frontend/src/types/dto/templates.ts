import type { BaseEntityDto, FileLinkDto } from "./common";

export type TemplateStatus = "draft" | "active" | "published" | "uploaded" | "linted" | "ready" | "archived" | "deprecated";

export interface TemplateScopeDto {
  level: "system" | "tenant" | "company" | "site" | string;
  company_id?: string | null;
  site_id?: string | null;
  label?: string | null;
  applicability?: string | null;
}

export interface TemplateVersionDto extends BaseEntityDto {
  template_id: string;
  version: string;
  status: TemplateStatus;
  comment?: string;
  file?: FileLinkDto | null;
}

export interface TemplateDto extends BaseEntityDto {
  code?: string;
  name: string;
  description?: string;
  category?: string;
  status?: TemplateStatus;
  scope?: TemplateScopeDto;
  tags?: string[];
  current_version?: TemplateVersionDto;
  current_version_id?: string;
  versions?: TemplateVersionDto[];
}

export interface UpdateTemplateDto {
  code?: string;
  name: string;
  description?: string;
  category?: string;
  status?: TemplateStatus;
  scope?: TemplateScopeDto;
  tags?: string[];
  version_id?: string;
}
