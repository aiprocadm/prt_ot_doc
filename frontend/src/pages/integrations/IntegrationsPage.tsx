import { RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAsyncResource } from "@/hooks/useAsyncResource";

type OutboxEntry = {
  id: string;
  event_type: string;
  destination: string;
  status: string;
  attempts: number;
  created_at: string;
  updated_at: string;
  next_attempt_at?: string | null;
  sent_at?: string | null;
  last_error?: Record<string, unknown> | null;
};

type OutboxEventEntry = {
  id: string;
  event_type: string;
  status: string;
  attempts: number;
  created_at: string;
  next_attempt_at?: string | null;
  last_error?: string | null;
};

type ReadinessResponse = {
  providers: Array<{ provider: string; health_status: string; configured: boolean; adapter?: string; reachable?: boolean | null }>;
  webhooks: { configured_total: number; enabled_total: number; delivery_failed_total: number };
};

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "—");

const IntegrationsPage = () => {
  const { data, setData, loading, error, reload } = useAsyncResource({
    loader: async () => {
      const [outboxResponse, eventResponse, readinessResponse] = await Promise.all([
        apiClient.get<{ items: OutboxEntry[] }>("/admin/outbox"),
        apiClient.get<{ items: OutboxEventEntry[] }>("/admin/outbox/events"),
        apiClient.get<ReadinessResponse>("/integrations/readiness"),
      ]);
      return {
        deliveries: outboxResponse.data.items ?? [],
        events: eventResponse.data.items ?? [],
        readiness: readinessResponse.data ?? null,
      };
    },
    initialData: {
      deliveries: [] as OutboxEntry[],
      events: [] as OutboxEventEntry[],
      readiness: null as ReadinessResponse | null,
    },
    errorMessage: "Не удалось загрузить интеграции",
  });

  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");

  const filteredDeliveries = useMemo(
    () => (statusFilter === "all" ? data.deliveries : data.deliveries.filter((item) => item.status === statusFilter)),
    [data.deliveries, statusFilter]
  );

  const summary = useMemo(() => {
    const failedDeliveries = data.deliveries.filter((item) => item.status === "failed" || item.status === "dead").length;
    const failedEvents = data.events.filter((item) => item.status === "failed" || item.status === "poisoned").length;
    const sent = data.deliveries.filter((item) => item.status === "sent").length;
    return {
      deliveries: data.deliveries.length,
      failedDeliveries,
      failedEvents,
      sent
    };
  }, [data.deliveries, data.events]);

  const retryDelivery = async (id: string) => {
    setRetryingId(id);
    try {
      await apiClient.post(`/admin/outbox/${id}/retry`);
      await reload();
    } finally {
      setRetryingId(null);
    }
  };

  const retryEvent = async (id: string) => {
    setRetryingId(id);
    try {
      await apiClient.post(`/admin/outbox/events/${id}/requeue`);
      await reload();
    } finally {
      setRetryingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Интеграции"
        description="Delivery history, retry-safe обработка и прозрачность статусов интеграций через outbox/event pipeline."
      />
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка интеграций" /> : null}
      {!loading && !error && data.deliveries.length + data.events.length === 0 ? (
        <EmptyState title="Интеграционные события отсутствуют" description="После первых webhook/outbox операций здесь появится журнал доставок." />
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        <Card><CardContent className="py-6"><div className="text-sm text-muted-foreground">Всего доставок</div><div className="text-2xl font-semibold">{summary.deliveries}</div></CardContent></Card>
        <Card><CardContent className="py-6"><div className="text-sm text-muted-foreground">Успешно отправлено</div><div className="text-2xl font-semibold">{summary.sent}</div></CardContent></Card>
        <Card><CardContent className="py-6"><div className="text-sm text-muted-foreground">Сбой доставки</div><div className="text-2xl font-semibold">{summary.failedDeliveries}</div></CardContent></Card>
        <Card><CardContent className="py-6"><div className="text-sm text-muted-foreground">Проблемные события</div><div className="text-2xl font-semibold">{summary.failedEvents}</div></CardContent></Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Provider readiness</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <Card><CardContent className="py-4"><div className="text-sm text-muted-foreground">Webhook endpoints</div><div className="text-xl font-semibold">{data.readiness?.webhooks.configured_total ?? 0}</div></CardContent></Card>
            <Card><CardContent className="py-4"><div className="text-sm text-muted-foreground">Enabled endpoints</div><div className="text-xl font-semibold">{data.readiness?.webhooks.enabled_total ?? 0}</div></CardContent></Card>
            <Card><CardContent className="py-4"><div className="text-sm text-muted-foreground">Failed deliveries</div><div className="text-xl font-semibold">{data.readiness?.webhooks.delivery_failed_total ?? 0}</div></CardContent></Card>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Provider</TableHead>
                <TableHead>Adapter</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Configured</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.readiness?.providers.map((item) => (
                <TableRow key={item.provider}>
                  <TableCell className="font-medium">{item.provider}</TableCell>
                  <TableCell>{item.adapter ?? "contract-only"}</TableCell>
                  <TableCell><StatusBadge status={item.health_status} /></TableCell>
                  <TableCell>{item.configured ? "yes" : "no"}</TableCell>
                </TableRow>
              )) ?? null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base">Outbound delivery history</CardTitle>
            <select className="h-9 rounded-md border px-3 text-sm" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">Все статусы</option>
              <option value="pending">pending</option>
              <option value="failed">failed</option>
              <option value="dead">dead</option>
              <option value="sent">sent</option>
            </select>
          </div>
          <Button variant="outline" onClick={() => void reload()} disabled={loading}>Обновить</Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Событие</TableHead>
                <TableHead>Назначение</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Попытки</TableHead>
                <TableHead>Тайминг</TableHead>
                <TableHead className="text-right">Действие</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredDeliveries.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>
                    <div className="font-medium">{item.event_type}</div>
                    <div className="text-xs text-muted-foreground">{item.id}</div>
                  </TableCell>
                  <TableCell className="max-w-[320px] truncate">{item.destination}</TableCell>
                  <TableCell><StatusBadge status={item.status} /></TableCell>
                  <TableCell>{item.attempts}</TableCell>
                  <TableCell>
                    <div className="text-sm">created: {formatDateTime(item.created_at)}</div>
                    <div className="text-xs text-muted-foreground">next: {formatDateTime(item.next_attempt_at)}</div>
                    <div className="text-xs text-muted-foreground">sent: {formatDateTime(item.sent_at)}</div>
                  </TableCell>
                  <TableCell className="text-right">
                    {(item.status === "failed" || item.status === "dead") ? (
                      <Can permission={PERMISSIONS.ADMIN_OUTBOX_MANAGE}>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void retryDelivery(item.id)}
                          disabled={retryingId === item.id}
                        >
                          <RotateCcw className="mr-2 h-4 w-4" /> Retry
                        </Button>
                      </Can>
                    ) : (
                      <span className="text-xs text-muted-foreground">{item.last_error ? "есть ошибка" : "—"}</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Integration event pipeline</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Attempts</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Ошибка</TableHead>
                <TableHead className="text-right">Действие</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.events.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>
                    <div className="font-medium">{item.event_type}</div>
                    <div className="text-xs text-muted-foreground">{item.id}</div>
                  </TableCell>
                  <TableCell><StatusBadge status={item.status} /></TableCell>
                  <TableCell>{item.attempts}</TableCell>
                  <TableCell>{formatDateTime(item.created_at)}</TableCell>
                  <TableCell className="max-w-[280px] truncate text-xs text-muted-foreground">{item.last_error ?? "—"}</TableCell>
                  <TableCell className="text-right">
                    {(item.status === "failed" || item.status === "poisoned") ? (
                      <Can permission={PERMISSIONS.ADMIN_OUTBOX_MANAGE}>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void retryEvent(item.id)}
                          disabled={retryingId === item.id}
                        >
                          <RotateCcw className="mr-2 h-4 w-4" /> Requeue
                        </Button>
                      </Can>
                    ) : (
                      <span className="text-xs text-muted-foreground">{formatDateTime(item.next_attempt_at)}</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

export default IntegrationsPage;
