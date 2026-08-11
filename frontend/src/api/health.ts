import { apiClient } from "@/api/client";

export type HealthCheckStatus = "ok" | "degraded" | "failed";

/** One per-dependency result from GET /api/v1/health/comprehensive. */
export type HealthCheckItem = {
  name: string;
  status: HealthCheckStatus;
  error?: string | null;
  duration_ms: number;
  timestamp: string;
};

/** Drill-down health response (backend: HealthCheckComprehensiveResponse). */
export type HealthComprehensiveDto = {
  status: HealthCheckStatus;
  checks: Record<string, HealthCheckItem>;
  tenant_id?: string | null;
  timestamp: string;
};

export const healthApi = {
  /**
   * Per-dependency health drill-down. ``skip_cache`` forces a fresh probe
   * (bypasses the backend's 60s TTL); ``skip_slow`` omits the slower optional
   * checks (integrations/email).
   */
  getComprehensive: async (params?: {
    skip_cache?: boolean;
    skip_slow?: boolean;
  }): Promise<HealthComprehensiveDto> => {
    const response = await apiClient.get<HealthComprehensiveDto>(
      "/health/comprehensive",
      {
        params,
      },
    );
    return response.data;
  },
};
