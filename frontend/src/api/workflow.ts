import { apiClient } from "@/api/client";
import type { WorkflowDefinition, WorkflowInstance, WorkflowInstanceListItem, WorkflowTask } from "@/features/workflow/types";

export const workflowApi = {
  getDefinitions: async (): Promise<WorkflowDefinition[]> => {
    const { data } = await apiClient.get<WorkflowDefinition[]>("/workflow/definitions");
    return data;
  },
  getTasks: async (): Promise<WorkflowTask[]> => {
    const { data } = await apiClient.get<WorkflowTask[]>("/workflow/tasks");
    return data;
  },
  getInstances: async (): Promise<WorkflowInstanceListItem[]> => {
    const { data } = await apiClient.get<WorkflowInstanceListItem[]>("/workflow/instances");
    return data;
  },
  createDefinition: async (payload: Record<string, unknown>): Promise<void> => {
    await apiClient.post("/workflow/definitions", payload);
  },
  validateDefinition: async (payload: Record<string, unknown>): Promise<{ node_types?: string[] }> => {
    const { data } = await apiClient.post<{ node_types?: string[] }>("/workflow/definitions/validate", payload);
    return data;
  },
  publishVersion: async (versionId: string): Promise<void> => {
    await apiClient.post(`/workflow/versions/${versionId}/publish`);
  },
  archiveVersion: async (versionId: string): Promise<void> => {
    await apiClient.post(`/workflow/versions/${versionId}/archive`);
  },
  startInstance: async (definitionCode: string): Promise<WorkflowInstance> => {
    const { data } = await apiClient.post<WorkflowInstance>("/workflow/instances", {
      definition_code: definitionCode,
      entity_type: "document",
      entity_id: `doc-${Date.now()}`,
      context: { approved: true, initiator_id: "current-user", escalation_role: "safety_admin" }
    });
    return data;
  },
  getInstance: async (instanceId: string): Promise<WorkflowInstance> => {
    const { data } = await apiClient.get<WorkflowInstance>(`/workflow/instances/${instanceId}`);
    return data;
  },
  completeTask: async (taskId: string): Promise<void> => {
    await apiClient.post(`/workflow/tasks/${taskId}/complete`, { decision: "approve", payload: { approved: true } });
  },
  moveTask: async (taskId: string, mode: "delegate" | "escalate" | "reassign", reassignRole: string, reassignUserId: string): Promise<void> => {
    await apiClient.post(`/workflow/tasks/${taskId}/${mode}`, {
      ...(reassignUserId ? { assignee_user_id: reassignUserId } : {}),
      assignee_role_code: reassignRole || undefined
    });
  }
};

