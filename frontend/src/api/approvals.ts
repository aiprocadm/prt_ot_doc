import { apiClient } from "@/api/client";

export type ApprovalTask = {
  id: string;
  process_id?: string;
  instance_id?: string;
  status: string;
  due_at?: string | null;
  deadline_at?: string | null;
};

export type ApprovalProcess = {
  id: string;
  status: string;
  object_id?: string;
  entity_id?: string;
  current_step?: number;
};

export type ApprovalRoute = {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  applies_to: string;
  status: string;
};

export type ApprovalRouteCreatePayload = {
  code: string;
  name: string;
  description?: string | null;
  applies_to: string;
  conditions_json: Record<string, unknown>;
  is_default: boolean;
  status: string;
};

export const approvalsApi = {
  listMyTasks: async (status = "open") => {
    const { data } = await apiClient.get<{ items: ApprovalTask[] }>("/v1/approvals/tasks", {
      params: { mine: 1, status },
    });
    return data.items;
  },
  listProcesses: async (status?: string) => {
    const { data } = await apiClient.get<{ items: ApprovalProcess[] }>("/approvals", { params: { status } });
    return data.items;
  },
  startApproval: async (entity_type: "document" | "pack", entity_id: string, approval_route_id: string) => {
    const { data } = await apiClient.post("/approvals/start", { entity_type, entity_id, approval_route_id });
    return data;
  },
  decide: async (approvalId: string, action: "approve" | "reject" | "delegate" | "comment", body: Record<string, unknown>) => {
    const { data } = await apiClient.post(`/approvals/${approvalId}/${action}`, body);
    return data;
  },
  decideTask: async (taskId: string, action: "approve" | "reject", comment: string) => {
    const { data } = await apiClient.post(`/v1/approvals/tasks/${taskId}/decision`, {
      decision: action,
      comment,
    });
    return data;
  },
  delegateTask: async (taskId: string, delegateTo: string, comment: string) => {
    const { data } = await apiClient.post(`/v1/approvals/tasks/${taskId}/decision`, {
      decision: "delegate",
      delegate_to_user_id: delegateTo,
      comment,
    });
    return data;
  },
  listRoutes: async () => {
    const { data } = await apiClient.get<{ items: ApprovalRoute[] }>("/approval-routes");
    return data.items;
  },
  createRoute: async (payload: ApprovalRouteCreatePayload) => {
    const { data } = await apiClient.post<{ id: string }>("/approval-routes", payload);
    return data;
  },
};
