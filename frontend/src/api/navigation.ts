import { apiClient } from "@/api/client";

export type TopNavKpi = {
  tasks: number;
  alerts: number;
};

export const getTopNavKpi = async (): Promise<TopNavKpi> => {
  const [taskResponse, notificationResponse] = await Promise.all([
    apiClient.get<Array<unknown>>("/workflow/tasks", { params: { assignee: "me" } }),
    apiClient.get<{ unread_count: number }>("/notifications", { params: { status: "unread", limit: 1 } })
  ]);

  return {
    tasks: taskResponse.data.length,
    alerts: notificationResponse.data.unread_count ?? 0
  };
};

export const sendUxMetric = async (name: string, payload?: Record<string, unknown>) => {
  try {
    await apiClient.post("/analytics/ux-events", { name, payload });
  } catch {
    // Optional endpoint: metric delivery is best-effort only.
  }
};

