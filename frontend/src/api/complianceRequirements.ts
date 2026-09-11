import { apiClient } from "@/api/client";
import type {
  ComplianceEvidenceCreateDto,
  ComplianceRequirementCreateDto,
  ComplianceRequirementDetailDto,
  ComplianceRequirementFiltersDto,
  ComplianceRequirementListDto,
} from "@/types/dto/complianceRequirements";

const BASE = "/compliance/requirements";

export interface OwnerOptionDto {
  id: string;
  full_name: string;
  email: string;
}

/**
 * Кандидаты в ответственные — активные пользователи арендатора. Ручка
 * админская: специалисту по ОТ она ответит 403, и тогда список пуст — поле
 * «Ответственный» остаётся незаполненным, а форма не падает.
 */
export const listOwnerOptions = async (): Promise<OwnerOptionDto[]> => {
  try {
    const { data } = await apiClient.get<{ items?: OwnerOptionDto[] }>(
      "/admin/users",
      { params: { is_active: true, limit: 200 } },
    );
    return data.items ?? [];
  } catch {
    return [];
  }
};

/** Срез-145 (B.18 разд. 19.2): реестр требований — обязательное ядро арендатора. */
export const complianceRequirementsApi = {
  list: async (
    filters: ComplianceRequirementFiltersDto = {},
  ): Promise<ComplianceRequirementListDto> => {
    const params: Record<string, string | boolean> = {};
    if (filters.npa_id) params.npa_id = filters.npa_id;
    if (filters.status) params.status = filters.status;
    if (filters.overdue) params.overdue = true;
    const { data } = await apiClient.get<ComplianceRequirementListDto>(BASE, {
      params,
    });
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
