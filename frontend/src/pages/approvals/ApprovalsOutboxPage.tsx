import { RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ApiError } from "@/types/dto/common";

type OutboxEntry = {
  id: string;
  event_type: string;
  destination: string;
  status: string;
  attempts: number;
  created_at: string;
  next_attempt_at?: string | null;
  sent_at?: string | null;
};

type OutboxEventEntry = {
  id: string;
  event_type: string;
  status: string;
  attempts: number;
  created_at: string;
  next_attempt_at?: string | null;
};

const APPROVAL_EVENT_PREFIX = "approval.";
const RETRYABLE_OUTBOX_STATUSES = new Set(["failed", "dead"]);
const RETRYABLE_EVENT_STATUSES = new Set(["failed", "poisoned"]);

const formatDateTime = (value?: string | null) => (value ? new Date(value).toLocaleString() : "—");

const isApprovalEvent = (eventType?: string) => typeof eventType === "string" && eventType.startsWith(APPROVAL_EVENT_PREFIX);

const ApprovalsOutboxPage = () => {
  const [deliveries, setDeliveries] = useState<OutboxEntry[]>([]);
  const [events, setEvents] = useState<OutboxEventEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [outboxResponse, eventsResponse] = await Promise.all([
        apiClient.get<{ items: OutboxEntry[] }>("/admin/outbox"),
        apiClient.get<{ items: OutboxEventEntry[] }>("/admin/outbox/events"),
      ]);
      setDeliveries((outboxResponse.data.items ?? []).filter((item) => isApprovalEvent(item.event_type)));
      setEvents((eventsResponse.data.items ?? []).filter((item) => isApprovalEvent(item.event_type)));
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить исходящие согласования", status: 0 });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const retryDelivery = async (id: string) => {
    setRetryingId(id);
    try {
      await apiClient.post(`/admin/outbox/${id}/retry`);
      await load();
    } finally {
      setRetryingId(null);
    }
  };

  const requeueEvent = async (id: string) => {
    setRetryingId(id);
    try {
      await apiClient.post(`/admin/outbox/events/${id}/requeue`);
      await load();
    } finally {
      setRetryingId(null);
    }
  };

  const hasData = useMemo(() => deliveries.length > 0 || events.length > 0, [deliveries.length, events.length]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Согласования: исходящие" }]} />
        <Button variant="outline" onClick={() => void load()} disabled={loading}>
          Обновить
        </Button>
      </div>

      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      {loading ? <LoadingScreen label="Загрузка исходящих согласований" /> : null}

      {!loading && !error && !hasData ? (
        <Card>
          <CardHeader>
            <CardTitle>Согласования: Исходящие</CardTitle>
          </CardHeader>
          <CardContent>
            <EmptyState
              title="Исходящие согласования пока отсутствуют"
              description="После запуска согласований здесь появятся статусы доставок и событий исходящей очереди." 
            />
          </CardContent>
        </Card>
      ) : null}

      {!loading && !error && deliveries.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Доставки согласований ({deliveries.length})</CardTitle>
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
                {deliveries.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <div className="font-medium">{item.event_type}</div>
                      <div className="text-xs text-muted-foreground">{item.id}</div>
                    </TableCell>
                    <TableCell className="max-w-[320px] truncate">{item.destination}</TableCell>
                    <TableCell><StatusBadge status={item.status} /></TableCell>
                    <TableCell>{item.attempts}</TableCell>
                    <TableCell>
                      <div className="text-sm">создано: {formatDateTime(item.created_at)}</div>
                      <div className="text-xs text-muted-foreground">следующая попытка: {formatDateTime(item.next_attempt_at)}</div>
                      <div className="text-xs text-muted-foreground">отправлено: {formatDateTime(item.sent_at)}</div>
                    </TableCell>
                    <TableCell className="text-right">
                      {RETRYABLE_OUTBOX_STATUSES.has(item.status) ? (
                        <Can permission={PERMISSIONS.ADMIN_OUTBOX_MANAGE}>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void retryDelivery(item.id)}
                            disabled={retryingId === item.id}
                          >
                            <RotateCcw className="mr-2 h-4 w-4" /> Повторить
                          </Button>
                        </Can>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}

      {!loading && !error && events.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>События согласований ({events.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Событие</TableHead>
                  <TableHead>Статус</TableHead>
                  <TableHead>Попытки</TableHead>
                  <TableHead>Создано</TableHead>
                  <TableHead className="text-right">Действие</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <div className="font-medium">{item.event_type}</div>
                      <div className="text-xs text-muted-foreground">{item.id}</div>
                    </TableCell>
                    <TableCell><StatusBadge status={item.status} /></TableCell>
                    <TableCell>{item.attempts}</TableCell>
                    <TableCell>{formatDateTime(item.created_at)}</TableCell>
                    <TableCell className="text-right">
                      {RETRYABLE_EVENT_STATUSES.has(item.status) ? (
                        <Can permission={PERMISSIONS.ADMIN_OUTBOX_MANAGE}>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void requeueEvent(item.id)}
                            disabled={retryingId === item.id}
                          >
                            <RotateCcw className="mr-2 h-4 w-4" /> В очередь
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
      ) : null}
    </div>
  );
};

export default ApprovalsOutboxPage;
