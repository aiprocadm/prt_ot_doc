import { apiClient } from "@/api/client";
import type {
  DocumentDependencyMapDto,
  DocumentReadinessDto,
  DocumentVersionCompareDto
} from "@/types/dto/documents";

export type WizardPipelineStatus = "queued" | "running" | "success" | "failed" | "canceled" | "done" | "error";

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
  data: Record<string, unknown>;
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

export type ReplaceReportResponse = {
  summary: ReplaceDryRunResponse["summary"];
  rows: ReplaceDiffItem[];
  total: number;
};

export const generateDocument = async (payload: GenerateDocumentRequest, idempotencyKey: string) => {
  const response = await apiClient.post<GenerationAcceptedResponse>("/documents/generate", payload, {
    headers: { "Idempotency-Key": idempotencyKey }
  });
  return response.data;
};

export const getGenerationTaskStatus = async (taskId: string) => {
  const response = await apiClient.get<TaskStatusResponse>(`/documents/tasks/${taskId}`);
  return response.data;
};

export const getDocumentReadiness = async (documentId: string) => {
  const response = await apiClient.get<DocumentReadinessDto>(`/documents/${documentId}/readiness`);
  return response.data;
};

export const compareDocumentVersions = async (
  documentId: string,
  leftVersionId: string,
  rightVersionId: string
) => {
  const response = await apiClient.get<DocumentVersionCompareDto>(
    `/documents/${documentId}/versions/compare`,
    { params: { left_version_id: leftVersionId, right_version_id: rightVersionId } }
  );
  return response.data;
};

export const getDocumentDependencyMap = async (documentId: string) => {
  const response = await apiClient.get<DocumentDependencyMapDto>(
    `/documents/${documentId}/dependency-map`
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

  const response = await apiClient.post<DocumentBatchRun>("/documents/batch", form);
  return response.data;
};

export const getDocumentBatch = async (batchId: string) => {
  const response = await apiClient.get<DocumentBatchRun>(`/documents/batch/${batchId}`);
  return response.data;
};

export const replaceDryRun = async (payload: {
  docxFile: File;
  replaceMapFile: File;
  idempotencyKey: string;
  options?: Record<string, unknown>;
}) => {
  const form = new FormData();
  form.append("docx_file", payload.docxFile);
  form.append("replace_map", payload.replaceMapFile);
  const response = await apiClient.post<ReplaceDryRunResponse>("/replace/dry-run", form, {
    headers: {
      "Idempotency-Key": payload.idempotencyKey,
      "X-Replace-Options": JSON.stringify({ dry_run: true, ...(payload.options ?? {}) })
    }
  });
  return response.data;
};

export const getReplaceReport = async (reportId: string, params?: { offset?: number; limit?: number }) => {
  const response = await apiClient.get<ReplaceReportResponse>(`/replace/reports/${reportId}`, { params });
  return response.data;
};
