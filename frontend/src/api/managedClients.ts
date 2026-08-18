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
  code:
    | "too_many_clients"
    | "too_many_signals"
    | "too_many_overdue"
    | "critical_client";
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

// BIZ-51: лента изменений у клиента (разд. 51.1–51.2).

export type ClientChangeKind =
  | "employee_hired"
  | "employee_left"
  | "position_added"
  | "site_added"
  | "org_structure_changed"
  | "activity_changed"
  | "deadline_approaching"
  | "regulation_changed";

export type ClientChangeStatus = "new" | "handled" | "dismissed";

/** Откуда узнали об изменении: доверие к записям разное. */
export type ClientChangeSource = "manual" | "import" | "data_quality";

export interface ClientChange {
  id: string;
  kind: ClientChangeKind;
  /** Человеческое название вида — приходит с сервера, вторую правду не заводим. */
  kind_title: string;
  happened_on: string;
  summary: string;
  details: string | null;
  status: ClientChangeStatus;
  handled_at: string | null;
  /** «Что теперь делать» из таблицы разд. 51.1 — смысл ленты. */
  suggestions: string[];
  source: ClientChangeSource | string;
}

export interface ClientChangePage {
  items: ClientChange[];
  total: number;
  summary: string;
}

/** Честный итог сбора сигналов Data Quality: слагаемые сходятся с found. */
export interface DqSignalsResult {
  found: number;
  recorded: number;
  already_in_feed: number;
  not_client_related: number;
  unparsed: number;
  deferred: number;
  truncated: boolean;
  summary: string;
}

// BIZ-51 срез-5: светофор соответствия (разд. 51.3).

export type TrafficLight = "green" | "yellow" | "red" | "not_measured";

export interface DirectionReadiness {
  direction: string;
  title: string;
  light: TrafficLight;
  /** Расшифровка обязательна: цвет без слов возвращает к гаданию. */
  reason: string;
  required: number;
  missing: number;
  lapsed: number;
  expiring: number;
}

export interface ClientReadiness {
  client_id: string;
  client_name: string;
  /** У Dedicated данные в другом арендаторе — честное not_aggregated. */
  aggregation: "aggregated" | "not_aggregated" | string;
  reason?: string | null;
  overall?: TrafficLight | null;
  directions: DirectionReadiness[];
}

// BIZ-51 срез-7/10: отчёты авто-аудита (разд. 51.3).

export interface ClientAuditReport {
  id: string;
  period_start: string;
  period_end: string;
  /** Итог светофора на дату отчёта. */
  overall: TrafficLight | string;
  /** «Что изменилось, что просрочено, что нужно сделать» — одним текстом. */
  summary: string;
  payload: {
    actions?: string[];
    [key: string]: unknown;
  };
}

export interface ClientAuditReportPage {
  items: ClientAuditReport[];
  total: number;
}

/** Итог ручного прогона аудита — по слагаемым. */
export interface AuditRunResult {
  created: number;
  already_current: number;
  skipped_dedicated: number;
  summary: string;
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
  /** Когда работа «от имени» истечёт (срез-10, Доп. №3 63.2). */
  expires_at?: string | null;
  seconds_left?: number | null;
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
  async portfolio(
    params: { limit?: number; offset?: number } = {},
  ): Promise<PortfolioPage> {
    const r = await apiClient.get<PortfolioPage>(base, {
      params: { limit: 100, offset: 0, ...params },
      ...silent,
    });
    return r.data;
  },

  async attention(): Promise<CrossClientAttention> {
    return (
      await apiClient.get<CrossClientAttention>(`${base}/attention`, silent)
    ).data;
  },

  async calendar(
    params: { days?: number; client_id?: string; kind?: DeadlineKind[] } = {},
  ): Promise<CrossClientCalendar> {
    const r = await apiClient.get<CrossClientCalendar>(`${base}/calendar`, {
      params: { days: 30, ...params },
      ...silent,
    });
    return r.data;
  },

  async workload(days = 30): Promise<SpecialistWorkloadResponse> {
    const r = await apiClient.get<SpecialistWorkloadResponse>(
      `${base}/workload`,
      {
        params: { days },
        ...silent,
      },
    );
    return r.data;
  },

  /** Клиенты, к которым У МЕНЯ есть доступ (основа переключателя). */
  async my(): Promise<MyManagedClientsResult> {
    const r = await apiClient.get<{
      items: MyManagedClient[];
      scoped_sections?: string[];
    }>(`${base}/my`, silent);
    return {
      items: r.data.items,
      scopedSections: r.data.scoped_sections ?? [],
    };
  },

  /** Войти в контекст клиента: бэкенд проверит грант и запишет след в аудит. */
  async enterContext(clientId: string): Promise<ClientContextResponse> {
    return (
      await apiClient.post<ClientContextResponse>(
        `${base}/${clientId}/context`,
        {},
      )
    ).data;
  },

  /**
   * Выйти из контекста. До среза-10 выход был чисто интерфейсным: баннер
   * исчезал, а на сервере работа «от имени» не имела конца — в журнале
   * доступа клиента это выглядело как бесконечная сессия.
   */
  async leaveContext(): Promise<void> {
    await apiClient.delete(`${base}/context`, silent);
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
    }>,
  ): Promise<ManagedClient> {
    return (await apiClient.patch<ManagedClient>(`${base}/${id}`, payload))
      .data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`${base}/${id}`);
  },

  /** Лента изменений клиента: свежие сверху (разд. 51.1). */
  async changes(
    clientId: string,
    params: { status?: ClientChangeStatus; limit?: number; offset?: number } = {},
  ): Promise<ClientChangePage> {
    const r = await apiClient.get<ClientChangePage>(
      `${base}/${clientId}/changes`,
      { params, ...silent },
    );
    return r.data;
  },

  /** Зафиксировать изменение руками (разд. 51.1): первый источник ленты. */
  async createChange(
    clientId: string,
    payload: {
      kind: ClientChangeKind;
      happened_on: string;
      summary: string;
      details?: string | null;
    },
  ): Promise<ClientChange> {
    return (
      await apiClient.post<ClientChange>(`${base}/${clientId}/changes`, payload)
    ).data;
  },

  /** Разобрать/отклонить запись или вернуть её в новые. */
  async patchChangeStatus(
    clientId: string,
    changeId: string,
    status: ClientChangeStatus,
  ): Promise<ClientChange> {
    return (
      await apiClient.patch<ClientChange>(
        `${base}/${clientId}/changes/${changeId}`,
        { status },
      )
    ).data;
  },

  /**
   * Собрать просрочки из проверок качества данных в ленты (разд. 51.2).
   * Повторный вызов безвреден по построению: личность находки включает дату
   * истечения, уже записанное сервер отсеивает сам.
   */
  async collectDqSignals(): Promise<DqSignalsResult> {
    return (await apiClient.post<DqSignalsResult>(`${base}/dq-signals`, {}))
      .data;
  },

  /** Светофор соответствия клиента: факт против эталона (разд. 51.3). */
  async readiness(clientId: string): Promise<ClientReadiness> {
    return (
      await apiClient.get<ClientReadiness>(
        `${base}/${clientId}/readiness`,
        silent,
      )
    ).data;
  },

  /** Карточка клиента. */
  async get(clientId: string): Promise<ManagedClient> {
    return (
      await apiClient.get<ManagedClient>(`${base}/${clientId}`, silent)
    ).data;
  },

  /** Отчёты авто-аудита клиента: свежие сверху (разд. 51.3). */
  async auditReports(
    clientId: string,
    params: { limit?: number; offset?: number } = {},
  ): Promise<ClientAuditReportPage> {
    return (
      await apiClient.get<ClientAuditReportPage>(
        `${base}/${clientId}/audit-reports`,
        { params, ...silent },
      )
    ).data;
  },

  /**
   * Собрать отчёты авто-аудита сейчас (по всем клиентам арендатора).
   * Повторный запуск в тот же день безвреден: отчёт за дату не пишется
   * второй раз — сервер честно скажет «уже есть за сегодня».
   */
  async runAudit(): Promise<AuditRunResult> {
    return (await apiClient.post<AuditRunResult>(`${base}/audit/run`, {})).data;
  },
};
