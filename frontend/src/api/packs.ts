import { apiClient } from "@/api/client";
import { tenantStorage } from "@/api/tenantStorage";

export const packsApi = {
  getProfiles: async <T>(): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>("/package-profiles");
    return data;
  },
  createProfile: async (payload: Record<string, unknown>): Promise<void> => {
    await apiClient.post("/package-profiles", payload);
  },
  getPresets: async <T>(): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>("/package-presets");
    return data;
  },
  createPreset: async (payload: Record<string, unknown>): Promise<void> => {
    await apiClient.post("/package-presets", payload);
  },
  validatePreset: async (id: string): Promise<void> => {
    await apiClient.post(`/package-presets/${id}:validate`);
  },
  getRunItems: async <T>(id: string): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>(`/pack-runs/${id}/items`);
    return data;
  },
  getRunTimeline: async <T>(id: string): Promise<T[]> => {
    const { data } = await apiClient.get<T[]>(`/pack-runs/${id}/timeline`);
    return data;
  },
  retryFailedRunItems: async (id: string): Promise<void> => {
    await apiClient.post(`/pack-runs/${id}:retry-failed`);
  },
  createRun: async (
    packagePresetId: string,
    rows: Array<Record<string, unknown>>,
    dryRun: boolean,
    idempotencyKey: string
  ): Promise<{ pack_run_id: string }> => {
    const tenant = tenantStorage.getTenant();
    const headers: Record<string, string> = { "Idempotency-Key": idempotencyKey };
    if (tenant?.slug) headers["X-Tenant"] = tenant.slug;
    const { data } = await apiClient.post<{ pack_run_id: string }>(
      "/pack-runs",
      {
        package_preset_id: packagePresetId,
        rows,
        selected_rows: rows.map((_, index) => index + 1),
        dry_run: dryRun
      },
      { headers }
    );
    return data;
  }
};

