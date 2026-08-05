import { apiClient } from "@/api/client";

// ── Types ──────────────────────────────────────────────────────────────────

export type ManagedClientMode = "lightweight" | "dedicated";
export type ContractStatus = "draft" | "active" | "suspended" | "terminated";

export interface ManagedClient {
  id: string;
  name: string;
  mode: ManagedClientMode;
  company_id?: string | null;
  dedicated_tenant_slug?: string | null;
  contract_status: ContractStatus;
  contract_no?: string | null;
  contract_starts_at?: string | null;
  contract_ends_at?: string | null;
  responsible_person_id?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PortfolioItem extends ManagedClient {
  contract_days_left?: number | null;
  contract_expiring: boolean;
}

export interface PortfolioSummary {
  total: number;
  active: number;
  draft: number;
  suspended: number;
  terminated: number;
  lightweight: number;
  dedicated: number;
  contracts_expiring: number;
}

export interface PortfolioPage {
  items: PortfolioItem[];
  summary: PortfolioSummary;
  total: number;
  limit: number;
  offset: number;
}

export type Severity = "low" | "medium" | "high" | "critical";
export type AggregationStatus = "aggregated" | "not_aggregated";
export type SignalKind =
  | "medical_overdue"
  | "ppe_overdue"
  | "training_overdue"
  | "contract_expiring"
  | "contacts_missing";

export interface AttentionSignal {
  kind: SignalKind;
  count: number;
  severity: Severity;
  title: string;
  action_hint: string;
}

export interface ClientAttention {
  client_id: string;
  client_name: string;
  aggregation: AggregationStatus;
  signals: AttentionSignal[];
  /** null = данные клиента не собирались (свой контур), а НЕ «ноль проблем». */
  total: number | null;
  severity: Severity | null;
  reason?: string | null;
}

export interface CrossClientAttentionSummary {
  clients_total: number;
  clients_with_signals: number;
  clients_not_aggregated: number;
  signals_total: number;
  critical_clients: number;
}

export interface CrossClientAttention {
  generated_at: string;
  summary: CrossClientAttentionSummary;
  items: ClientAttention[];
}

export type DeadlineKind = "medical" | "ppe" | "training" | "contract";

export interface DeadlineEvent {
  kind: DeadlineKind;
  title: string;
  due_date: string;
  client_id: string;
  client_name: string;
  subject: string;
  responsible_person_id?: string | null;
  days_left: number;
  overdue: boolean;
}

export interface DeadlineDay {
  due_date: string;
  overdue: boolean;
  events: DeadlineEvent[];
}

export interface CalendarSummary {
  events_total: number;
  overdue: number;
  due_today: number;
  upcoming: number;
  clients_touched: number;
}

export interface CrossClientCalendar {
  generated_at: string;
  horizon_days: number;
  summary: CalendarSummary;
  days: DeadlineDay[];
}

export interface OverloadReason {
  code: "too_many_clients" | "too_many_signals" | "too_many_overdue" | "critical_client";
  text: string;
}

export interface SpecialistWorkload {
  person_id: string;
  person_name?: string | null;
  /** Строка «клиенты без ответственного» — не специалист, но и не невидимка. */
  unassigned: boolean;
  clients_total: number;
  clients_critical: number;
  signals_total: number;
  overdue_deadlines: number;
  overloaded: boolean;
  overload_reasons: OverloadReason[];
}

export interface WorkloadThresholds {
  max_clients: number;
  max_signals: number;
  max_overdue: number;
}

export interface WorkloadSummary {
  specialists_total: number;
  overloaded: number;
  clients_unassigned: number;
}

export interface SpecialistWorkloadResponse {
  generated_at: string;
  thresholds: WorkloadThresholds;
  summary: WorkloadSummary;
  items: SpecialistWorkload[];
}

export interface MyManagedClient {
  client_id: string;
  client_name: string;
  mode: ManagedClientMode;
  all_modules: boolean;
  modules: string[];
}

export interface ClientContextResponse {
  client_id: string;
  client_name: string;
  mode: ManagedClientMode;
  all_modules: boolean;
  modules: string[];
  audit_recorded: boolean;
  scoped_sections: string[];
}

/**
 * Клиенты специалиста + разделы, где контекст УЖЕ работает как фильтр.
 * Список приходит с бэкенда, а не зашит здесь: захардкоженный на фронте, он
 * разъехался бы с кодом в день, когда фильтр добавят в новый раздел, — и
 * индикатор начал бы обещать больше, чем платформа делает.
 */
export interface MyManagedClientsResult {
  items: MyManagedClient[];
  scopedSections: string[];
}

// ── API ────────────────────────────────────────────────────────────────────

const base = "/managed-clients";

/**
 * Модуль ведения клиентов выключен по умолчанию: пока арендатор его не
 * подключил, бэкенд отвечает 404 (`MANAGED_CLIENTS_DISABLED`). Это штатное
 * состояние, а не сбой, поэтому глобальный тост тут не нужен — страница
 * показывает объяснение сама.
 */
const silent = { silentApiErrorToast: true } as const;

export const MANAGED_CLIENTS_DISABLED = "MANAGED_CLIENTS_DISABLED";

export const managedClientsApi = {
  async portfolio(params: { limit?: number; offset?: number } = {}): Promise<PortfolioPage> {
    const r = await apiClient.get<PortfolioPage>(base, {
      params: { limit: 100, offset: 0, ...params },
      ...silent
    });
    return r.data;
  },

  async attention(): Promise<CrossClientAttention> {
    return (await apiClient.get<CrossClientAttention>(`${base}/attention`, silent)).data;
  },

  async calendar(
    params: { days?: number; client_id?: string; kind?: DeadlineKind[] } = {}
  ): Promise<CrossClientCalendar> {
    const r = await apiClient.get<CrossClientCalendar>(`${base}/calendar`, {
      params: { days: 30, ...params },
      ...silent
    });
    return r.data;
  },

  async workload(days = 30): Promise<SpecialistWorkloadResponse> {
    const r = await apiClient.get<SpecialistWorkloadResponse>(`${base}/workload`, {
      params: { days },
      ...silent
    });
    return r.data;
  },

  /** Клиенты, к которым У МЕНЯ есть доступ (основа переключателя). */
  async my(): Promise<MyManagedClientsResult> {
    const r = await apiClient.get<{ items: MyManagedClient[]; scoped_sections?: string[] }>(
      `${base}/my`,
      silent
    );
    return { items: r.data.items, scopedSections: r.data.scoped_sections ?? [] };
  },

  /** Войти в контекст клиента: бэкенд проверит грант и запишет след в аудит. */
  async enterContext(clientId: string): Promise<ClientContextResponse> {
    return (await apiClient.post<ClientContextResponse>(`${base}/${clientId}/context`, {})).data;
  },

  async create(payload: {
    name: string;
    mode: ManagedClientMode;
    company_id?: string | null;
    dedicated_tenant_slug?: string | null;
    contract_no?: string | null;
    contract_ends_at?: string | null;
  }): Promise<ManagedClient> {
    return (await apiClient.post<ManagedClient>(base, payload)).data;
  },

  async update(
    id: string,
    payload: Partial<{
      name: string;
      mode: ManagedClientMode;
      company_id: string | null;
      dedicated_tenant_slug: string | null;
      contract_status: ContractStatus;
      contract_no: string | null;
      contract_ends_at: string | null;
      responsible_person_id: string | null;
      notes: string | null;
    }>
  ): Promise<ManagedClient> {
    return (await apiClient.patch<ManagedClient>(`${base}/${id}`, payload)).data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`${base}/${id}`);
  }
};
