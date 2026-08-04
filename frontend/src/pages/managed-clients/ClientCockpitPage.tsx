import { useCallback, useEffect, useState } from "react";

import {
  MANAGED_CLIENTS_DISABLED,
  managedClientsApi,
  type ClientAttention,
  type CrossClientAttention,
  type CrossClientCalendar,
  type DeadlineKind,
  type ManagedClientMode,
  type PortfolioItem,
  type PortfolioPage,
  type Severity,
} from "@/api/managedClients";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

// ── Словари ────────────────────────────────────────────────────────────────

const MODE_LABELS: Record<ManagedClientMode, string> = {
  lightweight: "В нашем контуре",
  dedicated: "Свой контур",
};

const CONTRACT_LABELS: Record<string, string> = {
  draft: "Черновик",
  active: "Действует",
  suspended: "Приостановлен",
  terminated: "Расторгнут",
};

const SEVERITY_LABELS: Record<Severity, string> = {
  critical: "Критично",
  high: "Важно",
  medium: "Средне",
  low: "Низкое",
};

const SEVERITY_VARIANT: Record<Severity, "default" | "destructive" | "secondary" | "outline"> = {
  critical: "destructive",
  high: "destructive",
  medium: "default",
  low: "secondary",
};

const selectClass =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

const asApiError = (err: unknown, fallback: string): ApiError =>
  err && typeof err === "object" && "message" in err
    ? (err as ApiError)
    : { status: 0, message: fallback };

const isModuleDisabled = (err: unknown): boolean =>
  Boolean(err && typeof err === "object" && (err as ApiError).code === MANAGED_CLIENTS_DISABLED);

// ── Блок внимания (что горит) ──────────────────────────────────────────────

const AttentionRow = ({ row }: { row: ClientAttention }) => {
  const notAggregated = row.aggregation === "not_aggregated";
  return (
    <div className="rounded-md border border-border p-3 space-y-2" data-testid="attention-row">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{row.client_name}</span>
        {row.severity ? (
          <Badge variant={SEVERITY_VARIANT[row.severity]}>{SEVERITY_LABELS[row.severity]}</Badge>
        ) : null}
        {notAggregated ? <Badge variant="outline">Данные не собраны</Badge> : null}
        {!notAggregated && row.signals.length === 0 ? (
          <span className="text-sm text-emerald-600">Без сигналов</span>
        ) : null}
      </div>
      {notAggregated && row.reason ? (
        <p className="text-xs text-muted-foreground">{row.reason}</p>
      ) : null}
      {row.signals.length > 0 ? (
        <ul className="space-y-1">
          {row.signals.map((signal) => (
            <li key={signal.kind} className="text-sm">
              <span className="font-medium">{signal.title}:</span> {signal.count}{" "}
              <span className="text-muted-foreground">— {signal.action_hint}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};

interface AttentionPanelProps {
  data: CrossClientAttention | null;
  loading: boolean;
  error: ApiError | null;
  onRetry: () => void;
}

const AttentionPanel = ({ data, loading, error, onRetry }: AttentionPanelProps) => (
  <Card>
    <CardHeader>
      <CardTitle className="text-base">Что горит по клиентам</CardTitle>
    </CardHeader>
    <CardContent className="space-y-3">
      <ErrorState error={error ?? undefined} onRetry={onRetry} />
      {loading ? <LoadingScreen label="Загрузка сводки внимания" /> : null}
      {!loading && !error && data ? (
        <>
          <div className="flex flex-wrap gap-4 text-sm" data-testid="attention-summary">
            <span>
              Клиентов: <strong>{data.summary.clients_total}</strong>
            </span>
            <span>
              С сигналами: <strong>{data.summary.clients_with_signals}</strong>
            </span>
            <span className={data.summary.critical_clients > 0 ? "text-destructive" : undefined}>
              Критичных: <strong>{data.summary.critical_clients}</strong>
            </span>
            {data.summary.clients_not_aggregated > 0 ? (
              <span className="text-muted-foreground">
                Данные не собраны: <strong>{data.summary.clients_not_aggregated}</strong>
              </span>
            ) : null}
          </div>
          {data.items.length === 0 ? (
            <EmptyState
              title="Нет клиентов"
              description="Добавьте первого клиента — сводка появится здесь."
            />
          ) : (
            <div className="space-y-2">
              {data.items.map((row) => (
                <AttentionRow key={row.client_id} row={row} />
              ))}
            </div>
          )}
        </>
      ) : null}
    </CardContent>
  </Card>
);

// ── Календарь дедлайнов ─────────────────────────────────────────────────────

const KIND_FILTERS: Array<{ value: DeadlineKind | "all"; label: string }> = [
  { value: "all", label: "Все типы" },
  { value: "medical", label: "Медосмотры" },
  { value: "ppe", label: "СИЗ" },
  { value: "training", label: "Обучение" },
  { value: "contract", label: "Договоры" },
];

interface CalendarPanelProps {
  clients: PortfolioItem[];
}

const CalendarPanel = ({ clients }: CalendarPanelProps) => {
  const [data, setData] = useState<CrossClientCalendar | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [days, setDays] = useState(30);
  const [clientId, setClientId] = useState("");
  const [kind, setKind] = useState<DeadlineKind | "all">("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await managedClientsApi.calendar({
          days,
          client_id: clientId || undefined,
          kind: kind === "all" ? undefined : [kind],
        })
      );
    } catch (err) {
      setError(asApiError(err, "Не удалось загрузить календарь"));
    } finally {
      setLoading(false);
    }
  }, [days, clientId, kind]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Календарь дедлайнов</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="cal-days">
              Горизонт
            </label>
            <select
              id="cal-days"
              className={selectClass}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <option value={7}>7 дней</option>
              <option value={30}>30 дней</option>
              <option value={90}>90 дней</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="cal-client">
              Клиент
            </label>
            <select
              id="cal-client"
              className={selectClass}
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
            >
              <option value="">Все клиенты</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="cal-kind">
              Тип
            </label>
            <select
              id="cal-kind"
              className={selectClass}
              value={kind}
              onChange={(e) => setKind(e.target.value as DeadlineKind | "all")}
            >
              {KIND_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка календаря" /> : null}
        {!loading && !error && data ? (
          <>
            <div className="flex flex-wrap gap-4 text-sm" data-testid="calendar-summary">
              <span className={data.summary.overdue > 0 ? "text-destructive" : undefined}>
                Просрочено: <strong>{data.summary.overdue}</strong>
              </span>
              <span>
                Сегодня: <strong>{data.summary.due_today}</strong>
              </span>
              <span>
                Впереди: <strong>{data.summary.upcoming}</strong>
              </span>
            </div>
            {data.days.length === 0 ? (
              <EmptyState
                title="Дедлайнов нет"
                description="В выбранном окне и по выбранным фильтрам сроков не найдено."
              />
            ) : (
              <div className="space-y-3">
                {data.days.map((day) => (
                  <div key={day.due_date} className="space-y-1" data-testid="calendar-day">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{formatDate(day.due_date)}</span>
                      {day.overdue ? <Badge variant="destructive">Просрочено</Badge> : null}
                    </div>
                    <ul className="space-y-1">
                      {day.events.map((event) => (
                        <li
                          key={`${event.client_id}-${event.kind}-${event.subject}-${event.due_date}`}
                          className="text-sm"
                        >
                          <span className="text-muted-foreground">{event.title}:</span>{" "}
                          {event.subject}{" "}
                          <span className="text-muted-foreground">— {event.client_name}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Портфель ────────────────────────────────────────────────────────────────

interface PortfolioPanelProps {
  data: PortfolioPage | null;
  loading: boolean;
  error: ApiError | null;
  onRetry: () => void;
  onCreated: () => void;
}

const PortfolioPanel = ({ data, loading, error, onRetry, onCreated }: PortfolioPanelProps) => {
  const [name, setName] = useState("");
  const [mode, setMode] = useState<ManagedClientMode>("lightweight");
  const [companyId, setCompanyId] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setFormError(null);
    try {
      await managedClientsApi.create({
        name: name.trim(),
        mode,
        company_id: mode === "lightweight" ? companyId.trim() || null : null,
        dedicated_tenant_slug: mode === "dedicated" ? tenantSlug.trim() || null : null,
      });
      setName("");
      setCompanyId("");
      setTenantSlug("");
      onCreated();
    } catch (err) {
      setFormError(asApiError(err, "Не удалось добавить клиента"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Портфель клиентов</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form className="flex flex-wrap items-end gap-2" onSubmit={handleCreate}>
          <div className="flex-1 min-w-[180px] space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="mc-name">
              Название клиента
            </label>
            <Input id="mc-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground" htmlFor="mc-mode">
              Режим ведения
            </label>
            <select
              id="mc-mode"
              className={selectClass}
              value={mode}
              onChange={(e) => setMode(e.target.value as ManagedClientMode)}
            >
              <option value="lightweight">{MODE_LABELS.lightweight}</option>
              <option value="dedicated">{MODE_LABELS.dedicated}</option>
            </select>
          </div>
          {mode === "lightweight" ? (
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground" htmlFor="mc-company">
                Организация клиента
              </label>
              <Input
                id="mc-company"
                value={companyId}
                onChange={(e) => setCompanyId(e.target.value)}
                placeholder="ID организации"
              />
            </div>
          ) : (
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground" htmlFor="mc-tenant">
                Контур клиента
              </label>
              <Input
                id="mc-tenant"
                value={tenantSlug}
                onChange={(e) => setTenantSlug(e.target.value)}
                placeholder="slug контура"
              />
            </div>
          )}
          <Button type="submit" disabled={saving || !name.trim()}>
            Добавить клиента
          </Button>
        </form>
        <ErrorState error={formError ?? undefined} />
        <ErrorState error={error ?? undefined} onRetry={onRetry} />
        {loading ? <LoadingScreen label="Загрузка портфеля" /> : null}

        {!loading && !error && data ? (
          <>
            <div className="flex flex-wrap gap-4 text-sm" data-testid="portfolio-summary">
              <span>
                Всего: <strong>{data.summary.total}</strong>
              </span>
              <span>
                Действующих: <strong>{data.summary.active}</strong>
              </span>
              <span>
                Черновиков: <strong>{data.summary.draft}</strong>
              </span>
              <span className={data.summary.contracts_expiring > 0 ? "text-destructive" : undefined}>
                Истекают договоры: <strong>{data.summary.contracts_expiring}</strong>
              </span>
            </div>
            {data.items.length === 0 ? (
              <EmptyState title="Портфель пуст" description="Клиенты ещё не заведены." />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Клиент</TableHead>
                    <TableHead>Режим</TableHead>
                    <TableHead>Договор</TableHead>
                    <TableHead>Срок</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-medium">{item.name}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {MODE_LABELS[item.mode] ?? item.mode}
                      </TableCell>
                      <TableCell>
                        <Badge variant={item.contract_status === "active" ? "default" : "outline"}>
                          {CONTRACT_LABELS[item.contract_status] ?? item.contract_status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className="flex items-center gap-2">
                          {item.contract_ends_at ? formatDate(item.contract_ends_at) : "—"}
                          {item.contract_expiring ? (
                            <Badge variant="destructive" className="text-xs">
                              {typeof item.contract_days_left === "number" &&
                              item.contract_days_left < 0
                                ? "Просрочен"
                                : "Истекает"}
                            </Badge>
                          ) : null}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Страница ────────────────────────────────────────────────────────────────

const ClientCockpitPage = () => {
  const [portfolio, setPortfolio] = useState<PortfolioPage | null>(null);
  const [attention, setAttention] = useState<CrossClientAttention | null>(null);
  const [loading, setLoading] = useState(false);
  const [portfolioError, setPortfolioError] = useState<ApiError | null>(null);
  const [attentionError, setAttentionError] = useState<ApiError | null>(null);
  const [moduleDisabled, setModuleDisabled] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setPortfolioError(null);
    setAttentionError(null);
    setModuleDisabled(false);
    const [portfolioResult, attentionResult] = await Promise.allSettled([
      managedClientsApi.portfolio(),
      managedClientsApi.attention(),
    ]);

    // Модуль выключен — это не сбой: показываем объяснение вместо двух ошибок.
    const disabled =
      (portfolioResult.status === "rejected" && isModuleDisabled(portfolioResult.reason)) ||
      (attentionResult.status === "rejected" && isModuleDisabled(attentionResult.reason));
    if (disabled) {
      setModuleDisabled(true);
      setLoading(false);
      return;
    }

    if (portfolioResult.status === "fulfilled") {
      setPortfolio(portfolioResult.value);
    } else {
      setPortfolioError(asApiError(portfolioResult.reason, "Не удалось загрузить портфель"));
    }
    if (attentionResult.status === "fulfilled") {
      setAttention(attentionResult.value);
    } else {
      setAttentionError(asApiError(attentionResult.reason, "Не удалось загрузить сводку внимания"));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Клиенты (аутсорсинг)"
        description="Единое окно: что горит по всем ведомым клиентам и состояние портфеля."
      />
      {moduleDisabled ? (
        <EmptyState
          title="Модуль не подключён"
          description="Ведение клиентов доступно на тарифе с модулем «Ведение клиентов (аутсорсинг)». Обратитесь к администратору платформы."
        />
      ) : (
        <>
          {/* Внимание — сверху: аутсорсер открывает окно ради «где горит»,
              а не ради алфавитного списка. */}
          <AttentionPanel
            data={attention}
            loading={loading}
            error={attentionError}
            onRetry={load}
          />
          {/* Календарь — между «что горит» и портфелем: он про ближайшие
              действия, а список клиентов нужен уже для навигации. */}
          <CalendarPanel clients={portfolio?.items ?? []} />
          <PortfolioPanel
            data={portfolio}
            loading={loading}
            error={portfolioError}
            onRetry={load}
            onCreated={load}
          />
        </>
      )}
    </div>
  );
};

export default ClientCockpitPage;
