import { apiClient } from "@/api/client";

export type ApprovalTask = {
  id: string;
  process_id: string;
  status: string;
  due_at: string | null;
};

export type ApprovalProcess = {
  id: string;
  status: string;
  object_id: string;
  current_step: number;
};

export const approvalsApi = {
  listMyTasks: async (status = "open") => {
    const { data } = await apiClient.get<{ items: ApprovalTask[] }>("/v1/approvals/tasks", {
      params: { mine: true, status },
    });
    return data.items;
  },
  listProcesses: async (status?: string) => {
    const { data } = await apiClient.get<{ items: ApprovalProcess[] }>("/v1/approvals/processes", {
      params: { status },
    });
    return data.items;
  },
  decideTask: async (taskId: string, decision: "approve" | "reject", comment?: string) => {
    const { data } = await apiClient.post(`/v1/approvals/tasks/${taskId}:decide`, { decision, comment });
    return data;
  },
  delegateTask: async (taskId: string, to_user_id: string, reason?: string) => {
    const { data } = await apiClient.post(`/v1/approvals/tasks/${taskId}:delegate`, { to_user_id, reason });
    return data;
  },
};
