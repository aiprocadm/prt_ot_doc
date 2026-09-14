import { apiClient } from "@/api/client";
import type {
  ComplianceEvidenceCreateDto,
  ComplianceRequirementCreateDto,
  ComplianceRequirementDetailDto,
  ComplianceRequirementFiltersDto,
  ComplianceRequirementListDto,
  ComplianceRequirementOptionsDto,
  ComplianceRequirementUpdateDto,
} from "@/types/dto/complianceRequirements";

const BASE = "/compliance/requirements";

/** Срез-145 (B.18 разд. 19.2): реестр требований — обязательное ядро арендатора. */
export const complianceRequirementsApi = {
  list: async (
    filters: ComplianceRequirementFiltersDto = {},
  ): Promise<ComplianceRequirementListDto> => {
    const params: Record<string, string | boolean | number> = {};
    if (filters.npa_id) params.npa_id = filters.npa_id;
    if (filters.status) params.status = filters.status;
    if (filters.overdue) params.overdue = true;
    // Срез-195: страница. Ноль — законное смещение, поэтому проверяется
    // ОПРЕДЕЛЁННОСТЬ, а не истинность: `if (filters.offset)` молча терял бы
    // возврат на первую страницу.
    if (filters.limit !== undefined) params.limit = filters.limit;
    if (filters.offset !== undefined) params.offset = filters.offset;
    const { data } = await apiClient.get<ComplianceRequirementListDto>(BASE, {
      params,
    });
    return data;
  },
  /**
   * Справочники формы (срез-147): кандидаты в ответственные, площадки и роли —
   * своя ручка для ролей записи. Раньше форма ходила в админскую `/admin/users`
   * и у специалиста по ОТ получала 403, а площадку не давала выбрать вовсе.
   */
  options: async (): Promise<ComplianceRequirementOptionsDto> => {
    const { data } = await apiClient.get<ComplianceRequirementOptionsDto>(
      `${BASE}/options`,
    );
    return data;
  },
  get: async (id: string): Promise<ComplianceRequirementDetailDto> => {
    const { data } = await apiClient.get<ComplianceRequirementDetailDto>(
      `${BASE}/${id}`,
    );
    return data;
  },
  create: async (
    payload: ComplianceRequirementCreateDto,
  ): Promise<ComplianceRequirementDetailDto> => {
    const { data } = await apiClient.post<ComplianceRequirementDetailDto>(
      BASE,
      payload,
    );
    return data;
  },
  /** Правка (срез-147): код и статус не меняются — код ключ, статус меняют «Исполнено»/«Снять». */
  update: async (
    id: string,
    payload: ComplianceRequirementUpdateDto,
  ): Promise<ComplianceRequirementDetailDto> => {
    const { data } = await apiClient.patch<ComplianceRequirementDetailDto>(
      `${BASE}/${id}`,
      payload,
    );
    return data;
  },
  /** «Исполнено»: доказательство записано, контрольная дата сдвинута. */
  confirm: async (
    id: string,
    payload: ComplianceEvidenceCreateDto,
  ): Promise<ComplianceRequirementDetailDto> => {
    const { data } = await apiClient.post<ComplianceRequirementDetailDto>(
      `${BASE}/${id}/evidence`,
      payload,
    );
    return data;
  },
  /** «Снять с контроля»: акт отменён или процесс закрыт; строка остаётся. */
  retire: async (id: string): Promise<ComplianceRequirementDetailDto> => {
    const { data } = await apiClient.post<ComplianceRequirementDetailDto>(
      `${BASE}/${id}/retire`,
    );
    return data;
  },
};
