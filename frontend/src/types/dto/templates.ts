import type { BaseEntityDto, FileLinkDto } from "./common";

export type TemplateStatus = "draft" | "published" | "archived";

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
  tags?: string[];
  current_version?: TemplateVersionDto;
  versions?: TemplateVersionDto[];
}

export interface UpdateTemplateDto {
  code?: string;
  name: string;
  description?: string;
  category?: string;
  tags?: string[];
  version_id?: string;
}
