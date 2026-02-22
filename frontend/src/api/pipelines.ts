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
  error_payload?: Record<string, unknown> | null;
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
  status: string;
  inputs_json?: Record<string, unknown> | null;
  outputs_json?: Record<string, unknown> | null;
  created_by?: string | null;
  correlation_id?: string | null;
  step_runs: PipelineStepRun[];
  logs?: PipelineLog[];
  artifacts?: Record<string, unknown>;
};

export const listPipelineRuns = async (params?: Record<string, string>) => {
  const response = await apiClient.get<{ items: Array<{ id: string; status: string; profile_id?: string | null; created_by?: string | null; correlation_id?: string | null }> }>("/v1/jobs", { params });
  return response.data.items.map((item) => ({
    run_id: item.id,
    status: item.status,
    profile_id: item.profile_id,
    created_by: item.created_by,
    correlation_id: item.correlation_id,
    step_runs: []
  })) as PipelineRun[];
};

export const getPipelineRun = async (runId: string) => {
  const response = await apiClient.get<{ job: { id: string; status: string; profile_id?: string | null; created_by?: string | null; correlation_id?: string | null }; steps: Array<{ code: string; status: string; attempt: number; started_at?: string | null; ended_at?: string | null; error_code?: string | null; error_payload?: Record<string, unknown> | null }>; logs: PipelineLog[]; result?: { artifacts?: Record<string, unknown> } | null }>(`/v1/jobs/${runId}`);
  const d = response.data;
  return {
    run_id: d.job.id,
    status: d.job.status,
    profile_id: d.job.profile_id,
    created_by: d.job.created_by,
    correlation_id: d.job.correlation_id,
    step_runs: d.steps.map((s) => ({
      step_run_id: `${d.job.id}:${s.code}`,
      run_id: d.job.id,
      step_code: s.code,
      status: s.status,
      attempt: s.attempt,
      started_at: s.started_at,
      ended_at: s.ended_at,
      error_code: s.error_code,
      error_payload: s.error_payload
    })),
    logs: d.logs,
    artifacts: d.result?.artifacts
  } as PipelineRun;
};

export const retryPipelineRun = async (runId: string) => {
  await apiClient.post(`/v1/jobs/${runId}:retry`, { retry_failed_only: true });
  return getPipelineRun(runId);
};

export const cancelPipelineRun = async (runId: string) => {
  await apiClient.post(`/v1/jobs/${runId}:cancel`);
  return getPipelineRun(runId);
};

export const retryPipelineStepRun = async (runId: string, stepRunId: string) => {
  const stepId = stepRunId.includes(":") ? stepRunId.split(":").slice(1).join(":") : stepRunId;
  await apiClient.post(`/v1/jobs/${runId}/steps/${stepId}:rerun`);
  return getPipelineRun(runId);
};
