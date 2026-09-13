import { apiClient } from "@/api/client";
import type { ApiError } from "@/types/dto/common";
import type {
  AutomationRuleCreate,
  AutomationRulePage,
  AutomationRuleRead,
  AutomationRuleUpdate,
  DryRunIn,
  DryRunOut,
  EventTypePage,
  RecipientRolePage,
  RuleLibraryInstallOut,
  RuleLibraryPage,
  RuleTestOut,
  TriggerPage,
} from "@/types/dto/rules";

const BASE = "/rules";

export const isFeatureDisabledError = (error: unknown): boolean => {
  const e = error as Partial<ApiError> | null;
  return Boolean(
    e && e.status === 404 && /feature is not enabled/i.test(e.message ?? ""),
  );
};

export const rulesApi = {
  async eventTypes(): Promise<EventTypePage> {
    return (await apiClient.get<EventTypePage>(`${BASE}/event-types`)).data;
  },
  /**
   * Роли-получатели уведомлений словами — единый словарь сервера (срез-148).
   * Раньше форма держала свой список из пяти ролей и не показывала получателей
   * библиотечных правил (эколог, инженер ПБ).
   */
  async recipientRoles(): Promise<RecipientRolePage> {
    return (await apiClient.get<RecipientRolePage>(`${BASE}/recipient-roles`))
      .data;
  },
  /** Библиотека предустановленных правил по дисциплинам (BIZ-54-57 срез-4). */
  async library(): Promise<RuleLibraryPage> {
    return (await apiClient.get<RuleLibraryPage>(`${BASE}/library`)).data;
  },
  /** Выдать недостающие правила библиотеки существующему арендатору (срез-63). */
  async installLibrary(): Promise<RuleLibraryInstallOut> {
    return (
      await apiClient.post<RuleLibraryInstallOut>(`${BASE}/library/install`)
    ).data;
  },
  async list(
    params: { limit?: number; offset?: number } = {},
  ): Promise<AutomationRulePage> {
    const { data } = await apiClient.get<AutomationRulePage>(BASE, {
      params: { limit: 100, offset: 0, ...params },
    });
    return data;
  },
  async create(payload: AutomationRuleCreate): Promise<AutomationRuleRead> {
    return (await apiClient.post<AutomationRuleRead>(BASE, payload)).data;
  },
  async get(id: string): Promise<AutomationRuleRead> {
    return (await apiClient.get<AutomationRuleRead>(`${BASE}/${id}`)).data;
  },
  async update(
    id: string,
    payload: AutomationRuleUpdate,
  ): Promise<AutomationRuleRead> {
    return (await apiClient.patch<AutomationRuleRead>(`${BASE}/${id}`, payload))
      .data;
  },
  async remove(id: string): Promise<void> {
    await apiClient.delete(`${BASE}/${id}`);
  },
  async dryRun(payload: DryRunIn): Promise<DryRunOut> {
    return (await apiClient.post<DryRunOut>(`${BASE}/dry-run`, payload)).data;
  },
  async test(
    id: string,
    payload: { limit?: number } = {},
  ): Promise<RuleTestOut> {
    return (await apiClient.post<RuleTestOut>(`${BASE}/${id}/test`, payload))
      .data;
  },
  async triggers(
    params: { rule_id?: string; limit?: number; offset?: number } = {},
  ): Promise<TriggerPage> {
    const { data } = await apiClient.get<TriggerPage>(`${BASE}/triggers`, {
      params: { limit: 50, offset: 0, ...params },
    });
    return data;
  },
};
