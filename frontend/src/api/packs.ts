import { apiClient } from "@/api/client";
import { tenantStorage } from "@/api/tenantStorage";

/** Ответ проверки без записи (`POST /pack-runs:preview`). */
export interface PackRunPreviewProblem {
  code: string;
  message: string;
  blocking: boolean;
  rows: number[];
  rows_total: number;
}

export interface PackRunPreview {
  ready: boolean;
  score: number;
  documents_total: number;
  rows_total: number;
  rows_selected: number;
  rows_ready: number;
  problems: PackRunPreviewProblem[];
}

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
  /**
   * Срез-164: предварительная проверка без записи. Раньше мастер слал
   * `dry_run: true` в обычный запуск — схема такого поля не знает, сервер
   * молча его выбрасывал и создавал НАСТОЯЩИЙ прогон: документы писались,
   * а человеку показывали «Dry-run запущен». Проверка без записи у сервера
   * есть отдельной ручкой, она ничего не создаёт и требует только чтения.
   */
  previewRun: async (
    packagePresetId: string,
    rows: Array<Record<string, unknown>>,
  ): Promise<PackRunPreview> => {
    const { data } = await apiClient.post<PackRunPreview>(
      "/pack-runs:preview",
      {
        package_preset_id: packagePresetId,
        rows,
        selected_rows: rows.map((_, index) => index + 1),
      },
    );
    return data;
  },
  createRun: async (
    packagePresetId: string,
    rows: Array<Record<string, unknown>>,
    idempotencyKey: string,
  ): Promise<{ pack_run_id: string }> => {
    const tenant = tenantStorage.getTenant();
    const headers: Record<string, string> = {
      "Idempotency-Key": idempotencyKey,
    };
    if (tenant?.slug) headers["X-Tenant"] = tenant.slug;
    const { data } = await apiClient.post<{ pack_run_id: string }>(
      "/pack-runs",
      {
        package_preset_id: packagePresetId,
        rows,
        selected_rows: rows.map((_, index) => index + 1),
      },
      { headers },
    );
    return data;
  },
};
