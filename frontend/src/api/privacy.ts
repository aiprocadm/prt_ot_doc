import { apiClient } from "@/api/client";

/**
 * Контур персональных данных (152-ФЗ). Срез-208: первая витрина у модуля,
 * который до этого жил только ручками.
 *
 * Срез-208 завёл реестр утечек, срез-209 — права субъекта (выгрузка, журнал
 * доступа, согласия, обезличивание). Без экрана остаются реестр обработки и
 * договоры поручения: их ведёт юрист раз в год, а не по обращению человека.
 */

export type BreachStage =
  | "notify_regulator"
  | "report_findings"
  | "notify_subjects";

export interface BreachDeadlineDto {
  stage: BreachStage;
  /** Подпись приходит с сервера: витрина не переводит коды сама. */
  title: string;
  due_at: string | null;
  done_at: string | null;
  status: "done" | "pending" | "overdue" | "no_deadline";
  status_title: string;
  /** Часы, а не дни: округление до даты дарит или отнимает часы. */
  hours_left: number | null;
}

export interface PdnBreachDto {
  id: string;
  summary: string;
  discovered_at: string | null;
  happened_at: string | null;
  affected_people: number | null;
  deadlines: BreachDeadlineDto[];
}

export interface PdnBreachListDto {
  items: PdnBreachDto[];
  /** Честная строка «платформа не отправляет уведомления сама». */
  notice: string;
}

export interface PdnBreachCreateDto {
  summary: string;
  discovered_at: string;
  happened_at?: string | null;
  affected_people?: number | null;
}

export const privacyApi = {
  breaches: async (): Promise<PdnBreachListDto> => {
    const { data } = await apiClient.get<PdnBreachListDto>("/privacy/breaches");
    return data;
  },
  registerBreach: async (
    payload: PdnBreachCreateDto,
  ): Promise<PdnBreachDto> => {
    const { data } = await apiClient.post<PdnBreachDto>(
      "/privacy/breaches",
      payload,
    );
    return data;
  },
  markBreachStep: async (
    breachId: string,
    stage: BreachStage,
  ): Promise<PdnBreachDto> => {
    const { data } = await apiClient.post<PdnBreachDto>(
      `/privacy/breaches/${breachId}/steps/${stage}`,
      {},
    );
    return data;
  },
};

// --------------------------------------------------------------------------
// Права субъекта ПДн (152-ФЗ разд. 66.2, срез-209)
// --------------------------------------------------------------------------

export interface PdnAccessLogEntryDto {
  id: string;
  action: string;
  actor_email: string | null;
  actor_role: string | null;
  purpose: string | null;
  occurred_at: string;
}

export interface PdnAccessLogPageDto {
  items: PdnAccessLogEntryDto[];
  total: number;
}

export interface PdnSubjectExportDto {
  format_version: string;
  generated_at: string;
  subject: { person_id: string; full_name: string; email: string | null };
  data_categories: string[];
  /** Честный признак: какая-то секция упёрлась в предел. Скрывать нельзя —
   *  человек получил бы неполную выгрузку, считая её полной. */
  truncated: boolean;
  max_items_per_section: number;
}

export interface PdnConsentEntryDto {
  id: string;
  purpose: string;
  legal_basis: string;
  version: number;
  status: string;
  granted_at: string;
  withdrawn_at: string | null;
}

export interface PdnConsentPageDto {
  items: PdnConsentEntryDto[];
  total: number;
  /** Пусто — обрабатывать человека больше не на чем, и обезличивание
   *  становится ОБЯЗАННОСТЬЮ. Правило считает сервер; экран обязан его
   *  показать, а не спрятать. */
  remaining_legal_bases: string[];
}

export interface PdnErasureResultDto {
  pseudonym: string;
  /** поле → было ли в нём значение до вычистки */
  scrubbed_fields: Record<string, boolean>;
  /** раздел → сколько записей сохранено обезличенными (сроки хранения) */
  retained_sections?: Record<string, number>;
}

export const privacySubjectApi = {
  exportSubject: async (personId: string): Promise<PdnSubjectExportDto> => {
    const { data } = await apiClient.get<PdnSubjectExportDto>(
      `/privacy/subjects/${personId}/export`,
    );
    return data;
  },
  accessLog: async (personId: string): Promise<PdnAccessLogPageDto> => {
    const { data } = await apiClient.get<PdnAccessLogPageDto>(
      `/privacy/subjects/${personId}/access-log`,
    );
    return data;
  },
  consents: async (personId: string): Promise<PdnConsentPageDto> => {
    const { data } = await apiClient.get<PdnConsentPageDto>(
      `/privacy/subjects/${personId}/consents`,
    );
    return data;
  },
  withdrawConsent: async (
    personId: string,
    purpose: string,
    reason: string,
  ): Promise<void> => {
    await apiClient.post(`/privacy/subjects/${personId}/consents/withdraw`, {
      purpose,
      reason,
    });
  },
  anonymize: async (
    personId: string,
    reason: string,
  ): Promise<PdnErasureResultDto> => {
    const { data } = await apiClient.post<PdnErasureResultDto>(
      `/privacy/subjects/${personId}/anonymize`,
      { reason },
    );
    return data;
  },
};
