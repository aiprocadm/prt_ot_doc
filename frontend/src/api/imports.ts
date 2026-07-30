import { apiClient } from "@/api/client";
import type { ApiError } from "@/types/dto/common";
import type {
  ImportApplyDto,
  ImportProfileDto,
  ImportBatchDto,
  ImportBatchRowDto,
  ImportPreviewDto,
  ImportTargetDto
} from "@/types/dto/imports";
import { downloadBlob } from "@/utils/download";

const BASE = "/imports";

/** Файл не влезает в синхронную ручку — предлагаем фоновую загрузку. */
export const isTooManyRowsError = (error: unknown): boolean => {
  const e = error as Partial<ApiError> | null;
  return Boolean(e && e.status === 422 && e.code === "IMPORT_FILE_TOO_MANY_ROWS");
};

/** Модуль импорта — default-OFF, и выключенный он отвечает 404. */
export const isFeatureDisabledError = (error: unknown): boolean => {
  const e = error as Partial<ApiError> | null;
  return Boolean(e && e.status === 404 && /not enabled/i.test(e.message ?? ""));
};

const withFile = (
  file: File,
  mapping?: Record<string, string>,
  createMissing?: string[],
  profile?: string | null
): FormData => {
  const form = new FormData();
  form.append("file", file);
  // Список справочников, а не флаг «создавать недостающее»: последнее звучит
  // безобидно ровно до того момента, когда импорт заводит юрлицо из опечатки.
  if (createMissing && createMissing.length > 0) {
    form.append("create_missing", createMissing.join(","));
  }
  if (profile) {
    form.append("profile", profile);
  }
  // Схема маппинга едет ОДНИМ полем-JSON: multipart не умеет вложенные объекты,
  // а разбирать `mapping[last_name]=Фамилия` на бэкенде значит писать свой парсер.
  if (mapping && Object.keys(mapping).length > 0) {
    form.append("mapping", JSON.stringify(mapping));
  }
  return form;
};

export const importsApi = {
  async profiles(target?: string): Promise<ImportProfileDto[]> {
    return (
      await apiClient.get<ImportProfileDto[]>(`${BASE}/profiles`, {
        params: target ? { target } : {}
      })
    ).data;
  },

  async targets(): Promise<ImportTargetDto[]> {
    return (await apiClient.get<ImportTargetDto[]>(`${BASE}/targets`)).data;
  },

  async downloadTemplate(targetCode: string): Promise<void> {
    const { data } = await apiClient.get<Blob>(`${BASE}/targets/${targetCode}/template`, {
      responseType: "blob"
    });
    downloadBlob(data, `import_${targetCode}_template.csv`);
  },

  async dryRun(
    targetCode: string,
    file: File,
    mapping?: Record<string, string>,
    profile?: string | null
  ): Promise<ImportPreviewDto> {
    return (
      await apiClient.post<ImportPreviewDto>(
        `${BASE}/${targetCode}/dry-run`,
        withFile(file, mapping, undefined, profile)
      )
    ).data;
  },

  async apply(
    targetCode: string,
    file: File,
    mapping?: Record<string, string>,
    createMissing?: string[],
    profile?: string | null
  ): Promise<ImportApplyDto> {
    return (
      await apiClient.post<ImportApplyDto>(
        `${BASE}/${targetCode}/apply`,
        withFile(file, mapping, createMissing, profile)
      )
    ).data;
  },

  async downloadReport(batchId: string): Promise<void> {
    const { data } = await apiClient.get<Blob>(`${BASE}/batches/${batchId}/report`, {
      responseType: "blob"
    });
    downloadBlob(data, `import_report_${batchId}.csv`);
  },

  async dryRunAsync(
    targetCode: string,
    file: File,
    mapping?: Record<string, string>
  ): Promise<ImportBatchDto> {
    return (
      await apiClient.post<ImportBatchDto>(
        `${BASE}/${targetCode}/dry-run-async`,
        withFile(file, mapping)
      )
    ).data;
  },

  async applyAsync(
    targetCode: string,
    file: File,
    mapping?: Record<string, string>
  ): Promise<ImportBatchDto> {
    return (
      await apiClient.post<ImportBatchDto>(
        `${BASE}/${targetCode}/apply-async`,
        withFile(file, mapping)
      )
    ).data;
  },

  async batch(batchId: string): Promise<ImportBatchDto> {
    return (await apiClient.get<ImportBatchDto>(`${BASE}/batches/${batchId}`)).data;
  },

  async batches(params: { target?: string; limit?: number } = {}): Promise<ImportBatchDto[]> {
    return (await apiClient.get<ImportBatchDto[]>(`${BASE}/batches`, { params })).data;
  },

  async batchRows(batchId: string, action?: string): Promise<ImportBatchRowDto[]> {
    return (
      await apiClient.get<ImportBatchRowDto[]>(`${BASE}/batches/${batchId}/rows`, {
        params: action ? { action } : {}
      })
    ).data;
  },

  async qualityCheck(batchId: string): Promise<ImportBatchDto> {
    return (await apiClient.post<ImportBatchDto>(`${BASE}/batches/${batchId}/quality-check`)).data;
  },

  async rollback(batchId: string): Promise<ImportBatchDto> {
    return (await apiClient.post<ImportBatchDto>(`${BASE}/batches/${batchId}/rollback`)).data;
  }
};
