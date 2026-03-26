import { FormEvent, useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { ApiError } from "@/types/dto/common";

type OutboxItem = { id: string; event_type: string; status: string; attempts: number };
type Endpoint = { id: string; url: string; enabled: boolean; subscribed_events: string[] };
type Delivery = { id: string; endpoint_id: string; event_id: string; status: string; attempts: number };

const OutboxPage = () => {
  const [items, setItems] = useState<OutboxItem[]>([]);
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [eventTypes, setEventTypes] = useState("DocumentGenerated,Signed,Exported,RiskAssessed,PPEIssued,TrainingCompleted");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [outbox, eps, dels] = await Promise.all([
        apiClient.get<{ items: OutboxItem[] }>("/admin/outbox/events"),
        apiClient.get<Endpoint[]>("/webhooks/endpoints"),
        apiClient.get<Delivery[]>("/webhooks/deliveries"),
      ]);
      setItems(outbox.data.items ?? []);
      setEndpoints(eps.data ?? []);
      setDeliveries(dels.data ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить данные интеграций");
    } finally {
      setLoading(false);
    }
  };

  const createEndpoint = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await apiClient.post("/webhooks/endpoints", {
        url,
        secret,
        enabled: true,
        subscribed_events: eventTypes.split(",").map((s) => s.trim()).filter(Boolean),
        timeout_ms: 8000,
        headers: {},
      });
      setUrl("");
      setSecret("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать webhook endpoint");
    }
  };

  const runTest = async (id: string) => {
    setError(null);
    try {
      await apiClient.post(`/webhooks/endpoints/${id}:test`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось выполнить тест webhook endpoint");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Integrations / Webhooks" }]} />
      <ErrorState
        error={
          error
            ? ({ status: 500, code: "integrations_load_error", message: error } as ApiError)
            : undefined
        }
        onRetry={() => void load()}
      />
      {loading ? <LoadingScreen label="Загрузка интеграций" /> : null}
      <Card>
        <CardHeader>
          <CardTitle>Webhook subscriptions</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={createEndpoint} className="mb-3 grid grid-cols-1 gap-2 md:grid-cols-4">
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example/webhook" required />
            <Input value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="secret" />
            <Input value={eventTypes} onChange={(e) => setEventTypes(e.target.value)} placeholder="event types" />
            <Button type="submit" disabled={loading}>Create</Button>
          </form>
          {endpoints.length === 0 ? (
            <EmptyState
              title="Webhook endpoints отсутствуют"
              description="Создайте первый endpoint, чтобы начать проверку delivery и интеграционных уведомлений."
            />
          ) : (
            <ul className="space-y-1 text-sm">
              {endpoints.map((item) => (
                <li key={item.id}>
                  {item.url} — <b>{item.enabled ? "enabled" : "disabled"}</b> ({item.subscribed_events.join(", ") || "all"})
                  <Button size="sm" className="ml-2" onClick={() => void runTest(item.id)} disabled={loading}>
                    Test
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Deliveries</CardTitle>
        </CardHeader>
        <CardContent>
          {deliveries.length === 0 ? (
            <EmptyState
              title="Delivery history пуста"
              description="После первой отправки webhook здесь появится история доставок."
            />
          ) : (
            <ul className="space-y-1 text-sm">
              {deliveries.slice(0, 20).map((item) => (
                <li key={item.id}>
                  {item.event_id} → {item.endpoint_id} — <b>{item.status}</b> (attempts: {item.attempts})
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Job outbox timeline / events emitted</CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <EmptyState
              title="Outbox events отсутствуют"
              description="После первых фоновых событий здесь появится timeline интеграционных сообщений."
            />
          ) : (
            <ul className="space-y-1 text-sm">
              {items.map((item) => (
                <li key={item.id}>
                  {item.event_type} — <b>{item.status}</b> (attempts: {item.attempts})
                </li>
              ))}
            </ul>
          )}
          <Button className="mt-3" onClick={() => void load()} disabled={loading}>
            Refresh
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default OutboxPage;
