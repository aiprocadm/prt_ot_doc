import { apiClient } from "@/api/client";
import { tenantStorage } from "@/api/tenantStorage";

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
  const tenant = tenantStorage.getTenant();
  if (!tenant?.slug) return;

  try {
    // Optional endpoint: metric delivery is best-effort only.
    await apiClient.post("/analytics/ux-events", { name, payload });
  } catch {
    // Optional endpoint: metric delivery is best-effort only (endpoint may be absent).
    // swallow — UX metrics must never surface errors to callers
  }
};
