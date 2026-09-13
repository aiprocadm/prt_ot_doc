import { apiClient } from "@/api/client";
import type { DocumentDto, DocumentReadinessDto } from "@/types/dto/documents";
import type { QualityReport } from "@/types/dto/documentQuality";

export type WizardPipelineStatus =
  | "queued"
  | "running"
  | "success"
  | "failed"
  | "canceled"
  | "done"
  | "error";

export type BatchItemStatus = "pending" | "running" | "success" | "failed";

export type DocumentBatchItem = {
  id: string;
  row_index: number;
  status: BatchItemStatus;
  error?: string | null;
  document_id?: string | null;
  document_version_id?: string | null;
  output_name?: string | null;
};

export type DocumentBatchRun = {
  id: string;
  status: WizardPipelineStatus;
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  items: DocumentBatchItem[];
};

export type GenerateDocumentRequest = {
  template_code: string;
  template_version: number;
  company_id: string;
  person_id?: string;
  data: Record<string, unknown>;
};

export type TemplateResolveRequest = {
  case_type?: string;
  document_type?: string;
  category?: string;
  company_id?: string;
  site_id?: string;
  person_id?: string;
};

export type TemplateResolveCandidate = {
  template_id: string;
  template_code: string;
  template_name: string;
  template_version: number;
  scope_level: string;
  scope_match: string;
  score: number;
  rationale: string[];
};

export type TemplateResolveResponse = {
  template_id: string;
  template_code: string;
  template_name: string;
  template_version: number;
  scope_level: string;
  resolution_chain: string[];
  alternatives: TemplateResolveCandidate[];
};

export type GenerationAcceptedResponse = {
  task_id: string;
  status_url: string;
  document_version_id?: string | null;
};

export type TaskStatusResponse = {
  task_id: string;
  status: WizardPipelineStatus;
  document_id?: string | null;
  document_version_id?: string | null;
  error?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type ReplaceDiffItem = {
  from: string;
  to: string;
  part: string;
  location: string;
  before: string;
  after: string;
  context: string;
  match_count: number;
};

export type ReplaceDryRunResponse = {
  job_id: string;
  report_id: string;
  summary: {
    matches: number;
    files: number;
    warnings: string[];
    pairs: Record<string, number>;
  };
  preview_samples: ReplaceDiffItem[];
};

export type MappingValidationResponse = {
  ok: boolean;
  missing_required_fields: string[];
  unmapped_source_fields: string[];
  summary: {
    source_total: number;
    mapped_total: number;
    missing_required_total: number;
    unmapped_source_total: number;
  };
};

export type ReplaceReportResponse = {
  summary: ReplaceDryRunResponse["summary"];
  rows: ReplaceDiffItem[];
  total: number;
};

export const generateDocument = async (
  payload: GenerateDocumentRequest,
  idempotencyKey: string,
) => {
  const response = await apiClient.post<GenerationAcceptedResponse>(
    "/documents/generate",
    payload,
    {
      headers: { "Idempotency-Key": idempotencyKey },
    },
  );
  return response.data;
};

export const resolveTemplateForQuickGenerate = async (
  payload: TemplateResolveRequest,
) => {
  const response = await apiClient.post<TemplateResolveResponse>(
    "/documents/template:resolve",
    payload,
  );
  return response.data;
};

export const getGenerationTaskStatus = async (taskId: string) => {
  const response = await apiClient.get<TaskStatusResponse>(
    `/documents/tasks/${taskId}`,
  );
  return response.data;
};

export const getDocumentReadiness = async (documentId: string) => {
  const response = await apiClient.get<DocumentReadinessDto>(
    `/documents/${documentId}/readiness`,
  );
  return response.data;
};

export const generateDocumentsBatch = async (payload: {
  file: File;
  templateCode: string;
  templateVersion: number;
  companyId: string;
  namingPattern?: string;
}) => {
  const form = new FormData();
  form.append("file", payload.file);
  form.append("template_code", payload.templateCode);
  form.append("template_version", String(payload.templateVersion));
  form.append("company_id", payload.companyId);
  if (payload.namingPattern) {
    form.append("naming_pattern", payload.namingPattern);
  }

  const response = await apiClient.post<DocumentBatchRun>(
    "/documents/batch",
    form,
  );
  return response.data;
};

export const getDocumentBatch = async (batchId: string) => {
  const response = await apiClient.get<DocumentBatchRun>(
    `/documents/batch/${batchId}`,
  );
  return response.data;
};

/**
 * Срез-154: `replaceDryRun` и `getReplaceReport` удалены.
 *
 * Они звали `POST /replace/dry-run` и `GET /replace/reports/{id}` — контракт,
 * которого у сервера нет: пробная замена «принеси свой DOCX и CSV-карту»
 * снята вместе со старым движком. Сегодня сервер умеет другое — заменить в
 * УЖЕ СОЗДАННОМ документе платформы по СОХРАНЁННОЙ карте замен
 * (`POST /documents/{document_version_id}/replace:dry-run` с
 * `replace_map_id`/`replace_map_code`, отчёт — `GET /replace-runs/{id}/report`).
 * Перенести старый сценарий на него нельзя: у произвольного файла с диска нет
 * версии документа, а витрины карт замен в продукте нет вовсе. Возврат шага —
 * решение владельца (нужна либо ручка для произвольного файла, либо экран
 * карт замен), поэтому функции убраны, а не «заглушены».
 */

export const checkDocumentQuality = async (payload: {
  data: Record<string, unknown>;
  required_fields?: string[];
  date_fields?: string[];
  numeric_fields?: string[];
  rendered_text?: string;
}) => {
  const response = await apiClient.post<QualityReport>(
    "/documents/quality:check",
    payload,
  );
  return response.data;
};

export const validateDocumentMapping = async (payload: {
  source_fields: string[];
  mapping: Record<string, string>;
  required_template_fields?: string[];
}) => {
  const response = await apiClient.post<MappingValidationResponse>(
    "/documents/mapping:validate",
    payload,
  );
  return response.data;
};

/**
 * Срез-142: короткий список документов арендатора для выбора в формах
 * (привязка к акту НПА). Та же ручка, что у экрана «Документы», — имя
 * документа здесь и там одно и то же.
 */
export const listDocumentsForPicker = async (): Promise<DocumentDto[]> => {
  const response = await apiClient.get<{ items?: DocumentDto[] }>(
    "/documents",
    { params: { page: 1, page_size: 200 } },
  );
  return response.data.items ?? [];
};
