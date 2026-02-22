import { apiClient } from "@/api/client";

export type PipelineStepRun = {
  step_run_id: string;
  run_id: string;
  step_code: string;
  status: string;
  attempt: number;
  started_at?: string | null;
  ended_at?: string | null;
  error_code?: string | null;
};

export type PipelineRun = {
  run_id: string;
  profile_id?: string | null;
  status: string;
  inputs_json?: Record<string, unknown> | null;
  outputs_json?: Record<string, unknown> | null;
  created_by?: string | null;
  correlation_id?: string | null;
  step_runs: PipelineStepRun[];
};

export const listPipelineRuns = async (params?: Record<string, string>) => {
  const response = await apiClient.get<PipelineRun[]>("/v1/pipelines/runs", { params });
  return response.data;
};

export const getPipelineRun = async (runId: string) => {
  const response = await apiClient.get<PipelineRun>(`/v1/pipelines/runs/${runId}`);
  return response.data;
};

export const retryPipelineRun = async (runId: string) => {
  const response = await apiClient.post<PipelineRun>(`/v1/pipelines/runs/${runId}:retry`);
  return response.data;
};

export const cancelPipelineRun = async (runId: string) => {
  const response = await apiClient.post<PipelineRun>(`/v1/pipelines/runs/${runId}:cancel`);
  return response.data;
};

export const retryPipelineStepRun = async (runId: string, stepRunId: string) => {
  const response = await apiClient.post<PipelineRun>(`/v1/pipelines/runs/${runId}/steps/${stepRunId}:retry`);
  return response.data;
};
