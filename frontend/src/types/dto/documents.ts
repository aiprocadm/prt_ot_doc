import type { BaseEntityDto, FileLinkDto } from "./common";
import type { CompanyDto } from "./companies";

export type DocumentStatus = "draft" | "generating" | "ready" | "error";

export interface DocumentVersionDto extends BaseEntityDto {
  document_id: string;
  status: DocumentStatus;
  storage: FileLinkDto | null;
  comment?: string;
}

export interface DocumentDto extends BaseEntityDto {
  name: string;
  type: string;
  company: CompanyDto;
  status: DocumentStatus;
  version: string;
  current_version_id?: string | null;
  template_id?: string;
  storage?: FileLinkDto | null;
  history?: DocumentVersionDto[];
}

export interface DocumentFiltersDto {
  search?: string;
  status?: DocumentStatus;
  company_id?: string;
  type?: string;
}

/** Этапы канонического контура документа (согласованы с document_core_profile). */
export interface DocumentPipelineStageDto {
  stage_id: string;
  label: string;
  complete: boolean;
  detail?: string | null;
}

/** TZ §9.5 — backend GET /documents/{id}/readiness */
export interface DocumentReadinessDto {
  score: number;
  blockers: string[];
  recommended_actions: string[];
  pipeline_stages?: DocumentPipelineStageDto[];
}
