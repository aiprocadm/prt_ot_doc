import { apiClient } from "@/api/client";
import type { WizardPipelineStatus } from "@/api/documents";

export type PipelineStepRun = {
  step_run_id: string;
  run_id: string;
  step_code: string;
  status: WizardPipelineStatus;
  attempt: number;
  started_at?: string | null;
  ended_at?: string | null;
  error_code?: string | null;
  error_payload?: Record<string, unknown> | null;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
};

export type PipelineLog = {
  timestamp: string;
  level: string;
  message: string;
  step_name?: string | null;
};

export type PipelineRun = {
  run_id: string;
  profile_id?: string | null;
  status: WizardPipelineStatus;
  inputs_json?: Record<string, unknown> | null;
  outputs_json?: Record<string, unknown> | null;
  created_by?: string | null;
  correlation_id?: string | null;
  step_runs: PipelineStepRun[];
  logs?: PipelineLog[];
  artifacts?: Record<string, unknown>;
};

export const listPipelineRuns = async (params?: Record<string, string>) => {
  const response = await apiClient.get<Array<{ run_id: string; status: WizardPipelineStatus; profile_id?: string | null; created_by?: string | null; correlation_id?: string | null; step_runs?: PipelineStepRun[] }>>("/pipelines/runs", { params });
  return response.data.map((item) => ({
    run_id: item.run_id,
    status: item.status,
    profile_id: item.profile_id,
    created_by: item.created_by,
    correlation_id: item.correlation_id,
    step_runs: item.step_runs ?? []
  })) as PipelineRun[];
};

export const getPipelineRun = async (runId: string) => {
  const response = await apiClient.get<PipelineRun>(`/pipelines/runs/${runId}`);
  const d = response.data;
  return {
    run_id: d.run_id,
    status: d.status,
    profile_id: d.profile_id,
    created_by: d.created_by,
    correlation_id: d.correlation_id,
    inputs_json: d.inputs_json,
    outputs_json: d.outputs_json,
    step_runs: d.step_runs,
    logs: d.logs,
    artifacts: d.artifacts
  } as PipelineRun;
};

export const retryPipelineRun = async (runId: string) => {
  await apiClient.post(`/pipelines/runs/${runId}:retry`);
  return getPipelineRun(runId);
};

export const cancelPipelineRun = async (runId: string) => {
  await apiClient.post(`/pipelines/runs/${runId}:cancel`);
  return getPipelineRun(runId);
};

export const retryPipelineStepRun = async (runId: string, stepRunId: string) => {
  const stepId = stepRunId.includes(":") ? stepRunId.split(":").slice(1).join(":") : stepRunId;
  await apiClient.post(`/pipelines/runs/${runId}/steps/${stepId}:retry`);
  return getPipelineRun(runId);
};

export const bulkActionPipelineRuns = async (runIds: string[], action: "retry" | "cancel") => {
  await apiClient.post(`/pipelines/runs:bulk?action=${action}`, runIds);
};
