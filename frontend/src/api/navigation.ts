import { apiClient } from "@/api/client";
import { tokenStorage } from "@/api/tokenStorage";
import { tenantStorage } from "@/api/tenantStorage";
import { appConfig } from "@/config/env";

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

  const token = tokenStorage.getAccessToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Tenant": tenant.slug
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/analytics/ux-events`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ name, payload })
    });
    if (!response.ok) {
      return;
    }
    await fetch(`${appConfig.apiBaseUrl}/analytics/ux-events`, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({ name, payload })
    });
  } catch {
    // Optional endpoint: metric delivery is best-effort only.
  }
};

