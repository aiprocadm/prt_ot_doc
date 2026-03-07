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

export const approvalsApi = {
  listMyTasks: async (status = "open") => {
    const { data } = await apiClient.get<{ items: ApprovalTask[] }>("/v1/approvals/tasks", {
      params: { mine: true, status },
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
};
