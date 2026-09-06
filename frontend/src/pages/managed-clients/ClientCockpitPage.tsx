import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  MANAGED_CLIENTS_DISABLED,
  managedClientsApi,
  type ClientAttention,
  type ClientChangeKind,
  type ClientChangePage,
  type ClientChangeStatus,
  type ClientReadiness,
  type CrossClientAttention,
  type CrossClientCalendar,
  type DeadlineKind,
  type ManagedClientMode,
  type PortfolioItem,
  type PortfolioPage,
  type Severity,
  type SpecialistWorkloadResponse,
} from "@/api/managedClients";
import { ClientContextSwitcher } from "@/components/common/ClientContextSwitcher";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LIGHT_LABELS, LIGHT_VARIANT } from "@/lib/lights";
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

const SEVERITY_VARIANT: Record<
  Severity,
  "default" | "destructive" | "secondary" | "outline"
> = {
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
  Boolean(
    err &&
      typeof err === "object" &&
      (err as ApiError).code === MANAGED_CLIENTS_DISABLED,
  );

// ── Блок внимания (что горит) ──────────────────────────────────────────────

const AttentionRow = ({ row }: { row: ClientAttention }) => {
  const notAggregated = row.aggregation === "not_aggregated";
  return (
    <div
      className="rounded-md border border-border p-3 space-y-2"
      data-testid="attention-row"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{row.client_name}</span>
        {row.severity ? (
          <Badge variant={SEVERITY_VARIANT[row.severity]}>
            {SEVERITY_LABELS[row.severity]}
          </Badge>
        ) : null}
        {notAggregated ? (
          <Badge variant="outline">Данные не собраны</Badge>
        ) : null}
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
              <span className="font-medium">{signal.title}:</span>{" "}
              {signal.count}{" "}
              <span className="text-muted-foreground">
                — {signal.action_hint}
              </span>
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

const AttentionPanel = ({
  data,
  loading,
  error,
  onRetry,
}: AttentionPanelProps) => (
  <Card>
    <CardHeader>
      <CardTitle className="text-base">Что горит по клиентам</CardTitle>
    </CardHeader>
    <CardContent className="space-y-3">
      <ErrorState error={error ?? undefined} onRetry={onRetry} />
      {loading ? <LoadingScreen label="Загрузка сводки внимания" /> : null}
      {!loading && !error && data ? (
        <>
          <div
            className="flex flex-wrap gap-4 text-sm"
            data-testid="attention-summary"
          >
            <span>
              Клиентов: <strong>{data.summary.clients_total}</strong>
            </span>
            <span>
              С сигналами: <strong>{data.summary.clients_with_signals}</strong>
            </span>
            <span
              className={
                data.summary.critical_clients > 0
                  ? "text-destructive"
                  : undefined
              }
            >
              Критичных: <strong>{data.summary.critical_clients}</strong>
            </span>
            {data.summary.clients_not_aggregated > 0 ? (
              <span className="text-muted-foreground">
                Данные не собраны:{" "}
                <strong>{data.summary.clients_not_aggregated}</strong>
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
  { value: "driver_license", label: "Удостоверения водителей" },
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
        }),
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
            <label
              className="text-xs text-muted-foreground"
              htmlFor="cal-client"
            >
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
            <div
              className="flex flex-wrap gap-4 text-sm"
              data-testid="calendar-summary"
            >
              <span
                className={
                  data.summary.overdue > 0 ? "text-destructive" : undefined
                }
              >
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
                  <div
                    key={day.due_date}
                    className="space-y-1"
                    data-testid="calendar-day"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium">
                        {formatDate(day.due_date)}
                      </span>
                      {day.overdue ? (
                        <Badge variant="destructive">Просрочено</Badge>
                      ) : null}
                    </div>
                    <ul className="space-y-1">
                      {day.events.map((event) => (
                        <li
                          key={`${event.client_id}-${event.kind}-${event.subject}-${event.due_date}`}
                          className="text-sm"
                        >
                          <span className="text-muted-foreground">
                            {event.title}:
                          </span>{" "}
                          {event.subject}{" "}
                          <span className="text-muted-foreground">
                            — {event.client_name}
                          </span>
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

// ── Лента изменений (BIZ-51, разд. 51.1–51.2) ──────────────────────────────

const SOURCE_LABELS: Record<string, string> = {
  manual: "Внесено вручную",
  import: "Импорт данных",
  data_quality: "Качество данных",
};

//: Виды изменений для формы ручной записи (таблица разд. 51.1).
//: `Record<ClientChangeKind, string>` намеренно: появись девятый вид на
//: сервере и в типах — компилятор сам потребует подпись, словарь не отстанет.
const CHANGE_KIND_LABELS: Record<ClientChangeKind, string> = {
  employee_hired: "Принят новый сотрудник",
  employee_left: "Уволен или переведён сотрудник",
  position_added: "Новая должность или рабочее место",
  site_added: "Новый объект или площадка",
  org_structure_changed: "Изменение оргструктуры",
  activity_changed: "Изменение вида деятельности или оборудования",
  deadline_approaching: "Наступает срок",
  regulation_changed: "Изменение НПА",
};

const CHANGE_STATUS_LABELS: Record<ClientChangeStatus, string> = {
  new: "Новое",
  handled: "Разобрано",
  dismissed: "Отклонено",
};

const CHANGE_STATUS_VARIANT: Record<
  ClientChangeStatus,
  "default" | "secondary" | "outline"
> = {
  new: "default",
  handled: "secondary",
  dismissed: "outline",
};

interface ChangeFeedPanelProps {
  clients: PortfolioItem[];
}

const ChangeFeedPanel = ({ clients }: ChangeFeedPanelProps) => {
  const [clientId, setClientId] = useState("");
  const [data, setData] = useState<ClientChangePage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [collecting, setCollecting] = useState(false);
  const [collectSummary, setCollectSummary] = useState<string | null>(null);
  const [collectError, setCollectError] = useState<ApiError | null>(null);
  // Форма ручной записи — первый источник разд. 51.2. Скрыта до клика:
  // всегда видимые четыре поля съели бы бюджет экрана (полей ≤ 7).
  const [adding, setAdding] = useState(false);
  const [newKind, setNewKind] = useState<ClientChangeKind>("employee_hired");
  const [newDate, setNewDate] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [newSummary, setNewSummary] = useState("");
  const [newDetails, setNewDetails] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<ApiError | null>(null);

  // Автовыбор первого клиента: пустая панель с приказом «выберите клиента»
  // стоила бы лишний клик каждому открытию окна.
  const effectiveClientId = clientId || clients[0]?.id || "";

  const load = useCallback(async () => {
    if (!effectiveClientId) {
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setData(await managedClientsApi.changes(effectiveClientId));
    } catch (err) {
      setError(asApiError(err, "Не удалось загрузить ленту изменений"));
    } finally {
      setLoading(false);
    }
  }, [effectiveClientId]);

  useEffect(() => {
    void load();
  }, [load]);

  const setStatus = async (changeId: string, status: ClientChangeStatus) => {
    // Ошибку покажет глобальный тост; лента просто останется прежней.
    await managedClientsApi
      .patchChangeStatus(effectiveClientId, changeId, status)
      .then(load)
      .catch(() => undefined);
  };

  const collect = async () => {
    setCollecting(true);
    setCollectSummary(null);
    setCollectError(null);
    try {
      const result = await managedClientsApi.collectDqSignals();
      // Итог остаётся НА ЭКРАНЕ, а не в тосте: специалист читает слагаемые
      // («уже в лентах», «не про клиентов») после того, как тост погас бы.
      setCollectSummary(result.summary);
      await load();
    } catch (err) {
      setCollectError(asApiError(err, "Не удалось собрать сигналы"));
    } finally {
      setCollecting(false);
    }
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSummary.trim() || !effectiveClientId) return;
    setSaving(true);
    setFormError(null);
    try {
      await managedClientsApi.createChange(effectiveClientId, {
        kind: newKind,
        happened_on: newDate,
        summary: newSummary.trim(),
        details: newDetails.trim() || null,
      });
      setNewSummary("");
      setNewDetails("");
      setAdding(false);
      await load();
    } catch (err) {
      setFormError(asApiError(err, "Не удалось записать изменение"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Лента изменений</CardTitle>
          {/* Обе кнопки вторичные намеренно: главные действия экрана не
              здесь (бюджет UX: главных действий ≤ 2). */}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAdding((v) => !v)}
              data-testid="add-change-button"
            >
              {adding ? "Свернуть форму" : "Добавить запись"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void collect()}
              disabled={collecting}
              data-testid="collect-dq-button"
            >
              {collecting ? "Собираем…" : "Собрать сигналы качества данных"}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <label
            className="text-xs text-muted-foreground"
            htmlFor="feed-client"
          >
            Клиент
          </label>
          <select
            id="feed-client"
            data-testid="feed-client-select"
            className={selectClass}
            value={effectiveClientId}
            onChange={(e) => setClientId(e.target.value)}
          >
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        {adding ? (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={handleAdd}
            data-testid="add-change-form"
          >
            <div className="space-y-1">
              <label
                className="text-xs text-muted-foreground"
                htmlFor="chg-kind"
              >
                Что изменилось
              </label>
              <select
                id="chg-kind"
                className={selectClass}
                value={newKind}
                onChange={(e) => setNewKind(e.target.value as ClientChangeKind)}
              >
                {Object.entries(CHANGE_KIND_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label
                className="text-xs text-muted-foreground"
                htmlFor="chg-date"
              >
                Дата изменения
              </label>
              {/* Дата САМОГО изменения, не записи: сроки считаются от неё
                  (правило среза-1). */}
              <Input
                id="chg-date"
                type="date"
                value={newDate}
                onChange={(e) => setNewDate(e.target.value)}
              />
            </div>
            <div className="flex-1 min-w-[200px] space-y-1">
              <label
                className="text-xs text-muted-foreground"
                htmlFor="chg-summary"
              >
                Что именно
              </label>
              <Input
                id="chg-summary"
                value={newSummary}
                onChange={(e) => setNewSummary(e.target.value)}
                placeholder="Принят слесарь Иванов"
              />
            </div>
            <div className="flex-1 min-w-[200px] space-y-1">
              <label
                className="text-xs text-muted-foreground"
                htmlFor="chg-details"
              >
                Подробности (необязательно)
              </label>
              <Input
                id="chg-details"
                value={newDetails}
                onChange={(e) => setNewDetails(e.target.value)}
              />
            </div>
            <Button
              type="submit"
              variant="outline"
              size="sm"
              disabled={saving || !newSummary.trim()}
            >
              Записать
            </Button>
          </form>
        ) : null}
        <ErrorState error={formError ?? undefined} />

        {collectSummary ? (
          <p className="text-sm" data-testid="dq-collect-result">
            {collectSummary}
          </p>
        ) : null}
        <ErrorState error={collectError ?? undefined} onRetry={collect} />

        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка ленты" /> : null}
        {!loading && !error && clients.length === 0 ? (
          <EmptyState
            title="Клиентов пока нет"
            description="Лента изменений появится вместе с первым ведомым клиентом."
          />
        ) : null}
        {!loading && !error && data ? (
          <>
            <p className="text-sm" data-testid="feed-summary">
              {data.summary}
            </p>
            {data.items.length === 0 ? (
              <EmptyState
                title="Изменений не зафиксировано"
                description="Сигналы приходят из импорта кадровых данных и проверок качества; запись руками — через API (экран — отдельным шагом)."
              />
            ) : (
              <Table data-testid="feed-table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Дата</TableHead>
                    <TableHead>Изменение</TableHead>
                    <TableHead>Источник</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead>Действия</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((change) => (
                    <TableRow key={change.id} data-testid="feed-row">
                      <TableCell className="whitespace-nowrap align-top">
                        {formatDate(change.happened_on)}
                      </TableCell>
                      <TableCell className="align-top">
                        <div>{change.summary}</div>
                        {/* Подсказки «что теперь делать» — смысл ленты
                            (таблица разд. 51.1), прятать их в раскрывашку
                            значило бы вернуть специалиста к гаданию. */}
                        <div className="text-xs text-muted-foreground">
                          {change.suggestions.join(" · ")}
                        </div>
                      </TableCell>
                      <TableCell className="align-top text-sm text-muted-foreground">
                        {SOURCE_LABELS[change.source] ?? change.source}
                      </TableCell>
                      <TableCell className="align-top">
                        <Badge variant={CHANGE_STATUS_VARIANT[change.status]}>
                          {CHANGE_STATUS_LABELS[change.status]}
                        </Badge>
                      </TableCell>
                      <TableCell className="space-x-1 align-top whitespace-nowrap">
                        {change.status === "new" ? (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() =>
                                void setStatus(change.id, "handled")
                              }
                            >
                              Разобрано
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                void setStatus(change.id, "dismissed")
                              }
                            >
                              Отклонить
                            </Button>
                          </>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => void setStatus(change.id, "new")}
                          >
                            Вернуть
                          </Button>
                        )}
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

// ── Светофор соответствия (BIZ-51 срез-6, разд. 51.3) ──────────────────────

interface ReadinessPanelProps {
  clients: PortfolioItem[];
}

const ReadinessPanel = ({ clients }: ReadinessPanelProps) => {
  const [clientId, setClientId] = useState("");
  const [data, setData] = useState<ClientReadiness | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const effectiveClientId = clientId || clients[0]?.id || "";

  const load = useCallback(async () => {
    if (!effectiveClientId) {
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setData(await managedClientsApi.readiness(effectiveClientId));
    } catch (err) {
      setError(asApiError(err, "Не удалось загрузить светофор соответствия"));
    } finally {
      setLoading(false);
    }
  }, [effectiveClientId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Соответствие эталону</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <label
            className="text-xs text-muted-foreground"
            htmlFor="readiness-client"
          >
            Клиент
          </label>
          <select
            id="readiness-client"
            data-testid="readiness-client-select"
            className={selectClass}
            value={effectiveClientId}
            onChange={(e) => setClientId(e.target.value)}
          >
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <ErrorState error={error ?? undefined} onRetry={load} />
        {loading ? <LoadingScreen label="Загрузка светофора" /> : null}
        {!loading && !error && clients.length === 0 ? (
          <EmptyState
            title="Клиентов пока нет"
            description="Светофор появится вместе с первым ведомым клиентом."
          />
        ) : null}
        {!loading && !error && data ? (
          data.aggregation === "not_aggregated" ? (
            // Честное «не собирается» вместо нулей — данные Dedicated-клиента
            // живут в его собственном контуре (правило «Центра внимания»).
            <EmptyState
              title="Данные не собраны"
              description={
                data.reason ?? "Данные ведутся в отдельном контуре клиента"
              }
            />
          ) : (
            <>
              {data.overall ? (
                <div
                  className="flex items-center gap-2 text-sm"
                  data-testid="readiness-overall"
                >
                  <span>Итог по измеренному:</span>
                  <Badge variant={LIGHT_VARIANT[data.overall]}>
                    {LIGHT_LABELS[data.overall]}
                  </Badge>
                </div>
              ) : null}
              <ul className="space-y-2">
                {data.directions.map((row) => (
                  <li
                    key={row.direction}
                    className="space-y-0.5"
                    data-testid="readiness-row"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{row.title}</span>
                      <Badge variant={LIGHT_VARIANT[row.light]}>
                        {LIGHT_LABELS[row.light]}
                      </Badge>
                    </div>
                    {/* Расшифровка обязательна: цвет без слов возвращает
                        специалиста к гаданию, почему он красный. */}
                    <div className="text-xs text-muted-foreground">
                      {row.reason}
                    </div>
                  </li>
                ))}
              </ul>
              {/* Скрытое названо, а не пропущено молча: дисциплины вне
                  редакции исполнителя — одной фразой под списком (срез-55). */}
              {data.not_applicable ? (
                <p
                  className="text-xs text-muted-foreground"
                  data-testid="readiness-not-applicable"
                >
                  {data.not_applicable}
                </p>
              ) : null}
            </>
          )
        ) : null}
      </CardContent>
    </Card>
  );
};

// ── Загрузка специалистов ───────────────────────────────────────────────────

interface WorkloadPanelProps {
  data: SpecialistWorkloadResponse | null;
  loading: boolean;
  error: ApiError | null;
  onRetry: () => void;
}

const WorkloadPanel = ({
  data,
  loading,
  error,
  onRetry,
}: WorkloadPanelProps) => (
  <Card>
    <CardHeader>
      <CardTitle className="text-base">Загрузка специалистов</CardTitle>
    </CardHeader>
    <CardContent className="space-y-3">
      <ErrorState error={error ?? undefined} onRetry={onRetry} />
      {loading ? <LoadingScreen label="Загрузка по специалистам" /> : null}
      {!loading && !error && data ? (
        <>
          <div
            className="flex flex-wrap gap-4 text-sm"
            data-testid="workload-summary"
          >
            <span>
              Специалистов: <strong>{data.summary.specialists_total}</strong>
            </span>
            <span
              className={
                data.summary.overloaded > 0 ? "text-destructive" : undefined
              }
            >
              Перегружено: <strong>{data.summary.overloaded}</strong>
            </span>
            {data.summary.clients_unassigned > 0 ? (
              <span className="text-destructive">
                Без ответственного:{" "}
                <strong>{data.summary.clients_unassigned}</strong>
              </span>
            ) : null}
          </div>
          {/* Пороги показываем рядом: «перегружен» без правила — повод для спора,
              а не для действия. */}
          <p className="text-xs text-muted-foreground">
            Порог перегруза: клиентов &gt; {data.thresholds.max_clients},
            сигналов &gt; {data.thresholds.max_signals}, просрочек &gt;{" "}
            {data.thresholds.max_overdue}, либо есть критический клиент.
          </p>
          {data.items.length === 0 ? (
            <EmptyState
              title="Нет данных"
              description="Назначьте ответственных специалистов клиентам."
            />
          ) : (
            <Table data-testid="workload-table">
              <TableHeader>
                <TableRow>
                  <TableHead>Специалист</TableHead>
                  <TableHead>Клиентов</TableHead>
                  <TableHead>Сигналов</TableHead>
                  <TableHead>Просрочено</TableHead>
                  <TableHead>Состояние</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((row) => (
                  <TableRow key={row.person_id} data-testid="workload-row">
                    <TableCell className="font-medium">
                      {row.unassigned
                        ? "Без ответственного"
                        : (row.person_name ?? row.person_id)}
                    </TableCell>
                    <TableCell>{row.clients_total}</TableCell>
                    <TableCell>{row.signals_total}</TableCell>
                    <TableCell>{row.overdue_deadlines}</TableCell>
                    <TableCell>
                      {row.overloaded ? (
                        <span className="flex flex-col gap-1">
                          <Badge variant="destructive" className="w-fit">
                            Перегруз
                          </Badge>
                          {row.overload_reasons.map((reason) => (
                            <span
                              key={reason.code}
                              className="text-xs text-muted-foreground"
                            >
                              {reason.text}
                            </span>
                          ))}
                        </span>
                      ) : (
                        <span className="text-sm text-muted-foreground">
                          В норме
                        </span>
                      )}
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

// ── Портфель ────────────────────────────────────────────────────────────────

interface PortfolioPanelProps {
  data: PortfolioPage | null;
  loading: boolean;
  error: ApiError | null;
  onRetry: () => void;
  onCreated: () => void;
}

const PortfolioPanel = ({
  data,
  loading,
  error,
  onRetry,
  onCreated,
}: PortfolioPanelProps) => {
  const [adding, setAdding] = useState(false);
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
        dedicated_tenant_slug:
          mode === "dedicated" ? tenantSlug.trim() || null : null,
      });
      setName("");
      setCompanyId("");
      setTenantSlug("");
      setAdding(false);
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
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Портфель клиентов</CardTitle>
          {/* Форма скрыта до клика (BIZ-60): всегда видимые три поля выводили
              экран из бюджета (8 полей при лимите 7). */}
          <Button size="sm" onClick={() => setAdding((v) => !v)}>
            {adding ? "Свернуть форму" : "Добавить клиента"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {adding ? (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={handleCreate}
          >
            <div className="flex-1 min-w-[180px] space-y-1">
              <label
                className="text-xs text-muted-foreground"
                htmlFor="mc-name"
              >
                Название клиента
              </label>
              <Input
                id="mc-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label
                className="text-xs text-muted-foreground"
                htmlFor="mc-mode"
              >
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
                <label
                  className="text-xs text-muted-foreground"
                  htmlFor="mc-company"
                >
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
                <label
                  className="text-xs text-muted-foreground"
                  htmlFor="mc-tenant"
                >
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
              Сохранить клиента
            </Button>
          </form>
        ) : null}
        <ErrorState error={formError ?? undefined} />
        <ErrorState error={error ?? undefined} onRetry={onRetry} />
        {loading ? <LoadingScreen label="Загрузка портфеля" /> : null}

        {!loading && !error && data ? (
          <>
            <div
              className="flex flex-wrap gap-4 text-sm"
              data-testid="portfolio-summary"
            >
              <span>
                Всего: <strong>{data.summary.total}</strong>
              </span>
              <span>
                Действующих: <strong>{data.summary.active}</strong>
              </span>
              <span>
                Черновиков: <strong>{data.summary.draft}</strong>
              </span>
              <span
                className={
                  data.summary.contracts_expiring > 0
                    ? "text-destructive"
                    : undefined
                }
              >
                Истекают договоры:{" "}
                <strong>{data.summary.contracts_expiring}</strong>
              </span>
            </div>
            {data.items.length === 0 ? (
              <EmptyState
                title="Портфель пуст"
                description="Клиенты ещё не заведены."
              />
            ) : (
              <Table data-testid="portfolio-table">
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
                      <TableCell className="font-medium">
                        {/* Имя ведёт в карточку: отчёты авто-аудита живут
                            там — кокпит заполнен до предела (срез-6). */}
                        <Link
                          to={`/managed-clients/${item.id}`}
                          className="underline-offset-4 hover:underline"
                        >
                          {item.name}
                        </Link>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {MODE_LABELS[item.mode] ?? item.mode}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            item.contract_status === "active"
                              ? "default"
                              : "outline"
                          }
                        >
                          {CONTRACT_LABELS[item.contract_status] ??
                            item.contract_status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className="flex items-center gap-2">
                          {item.contract_ends_at
                            ? formatDate(item.contract_ends_at)
                            : "—"}
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
  const [workload, setWorkload] = useState<SpecialistWorkloadResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [portfolioError, setPortfolioError] = useState<ApiError | null>(null);
  const [attentionError, setAttentionError] = useState<ApiError | null>(null);
  const [workloadError, setWorkloadError] = useState<ApiError | null>(null);
  const [moduleDisabled, setModuleDisabled] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setPortfolioError(null);
    setAttentionError(null);
    setWorkloadError(null);
    setModuleDisabled(false);
    const [portfolioResult, attentionResult, workloadResult] =
      await Promise.allSettled([
        managedClientsApi.portfolio(),
        managedClientsApi.attention(),
        managedClientsApi.workload(),
      ]);

    // Модуль выключен — это не сбой: показываем объяснение вместо двух ошибок.
    const disabled =
      (portfolioResult.status === "rejected" &&
        isModuleDisabled(portfolioResult.reason)) ||
      (attentionResult.status === "rejected" &&
        isModuleDisabled(attentionResult.reason)) ||
      (workloadResult.status === "rejected" &&
        isModuleDisabled(workloadResult.reason));
    if (disabled) {
      setModuleDisabled(true);
      setLoading(false);
      return;
    }

    if (portfolioResult.status === "fulfilled") {
      setPortfolio(portfolioResult.value);
    } else {
      setPortfolioError(
        asApiError(portfolioResult.reason, "Не удалось загрузить портфель"),
      );
    }
    if (attentionResult.status === "fulfilled") {
      setAttention(attentionResult.value);
    } else {
      setAttentionError(
        asApiError(
          attentionResult.reason,
          "Не удалось загрузить сводку внимания",
        ),
      );
    }
    if (workloadResult.status === "fulfilled") {
      setWorkload(workloadResult.value);
    } else {
      setWorkloadError(
        asApiError(
          workloadResult.reason,
          "Не удалось загрузить загрузку специалистов",
        ),
      );
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
      {/* Переключатель и индикатор контекста — ВЫШЕ данных: если специалист
          работает от имени клиента, он обязан видеть это, не прокручивая. */}
      <ClientContextSwitcher onContextChange={() => void load()} />
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
          {/* Лента — после календаря: сроки говорят «когда», лента — «что
              изменилось и что теперь делать» (разд. 51.1). */}
          <ChangeFeedPanel clients={portfolio?.items ?? []} />
          {/* Светофор — после ленты: события разобраны, дальше вопрос
              «а всё ли у клиента есть» (разд. 51.3). */}
          <ReadinessPanel clients={portfolio?.items ?? []} />
          <PortfolioPanel
            data={portfolio}
            loading={loading}
            error={portfolioError}
            onRetry={load}
            onCreated={load}
          />
          {/* Загрузка — после портфеля: сначала «что горит» и сроки,
              потом вопрос «кто это тянет». */}
          <WorkloadPanel
            data={workload}
            loading={loading}
            error={workloadError}
            onRetry={load}
          />
        </>
      )}
    </div>
  );
};

export default ClientCockpitPage;
