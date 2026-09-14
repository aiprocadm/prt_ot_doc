import { statusLabel } from "@/components/common/StatusBadge";
import { FormEvent, useEffect, useState } from "react";

import { integrationsApi } from "@/api/integrations";
import { webhooksApi } from "@/api/webhooks";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { ApiError } from "@/types/dto/common";

type OutboxItem = {
  id: string;
  event_type: string;
  status: string;
  attempts: number;
};
type Endpoint = {
  id: string;
  url: string;
  enabled: boolean;
  subscribed_events: string[];
};
type Delivery = {
  id: string;
  endpoint_id: string;
  event_id: string;
  status: string;
  attempts: number;
};

const OutboxPage = () => {
  const [items, setItems] = useState<OutboxItem[]>([]);
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [eventTypes, setEventTypes] = useState(
    "DocumentGenerated,Signed,Exported,RiskAssessed,PPEIssued,TrainingCompleted",
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [outbox, eps, dels] = await Promise.all([
        integrationsApi.getOutboxEvents<OutboxItem>(),
        webhooksApi.getEndpoints<Endpoint>(),
        webhooksApi.getDeliveries<Delivery>(),
      ]);
      setItems(outbox.items ?? []);
      setEndpoints(eps ?? []);
      setDeliveries(dels ?? []);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Не удалось загрузить данные интеграций",
      );
    } finally {
      setLoading(false);
    }
  };

  const createEndpoint = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await webhooksApi.createEndpoint({
        url,
        secret,
        enabled: true,
        subscribed_events: eventTypes
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        timeout_ms: 8000,
        headers: {},
      });
      setUrl("");
      setSecret("");
      await load();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Не удалось создать точку вебхука",
      );
    }
  };

  const runTest = async (id: string) => {
    setError(null);
    try {
      await webhooksApi.testEndpoint(id);
      await load();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Не удалось выполнить тест точки вебхука",
      );
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="space-y-4">
      <Breadcrumb
        items={[
          { label: "Главная", to: "/dashboard" },
          { label: "Интеграции и вебхуки" },
        ]}
      />
      <ErrorState
        error={
          error
            ? ({
                status: 400,
                code: "integrations_load_error",
                message: error,
              } as ApiError)
            : undefined
        }
        onRetry={() => void load()}
      />
      {loading ? <LoadingScreen label="Загрузка интеграций" /> : null}
      <Card>
        <CardHeader>
          <CardTitle>Подписки на вебхуки</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={createEndpoint}
            className="mb-3 grid grid-cols-1 gap-2 md:grid-cols-4"
          >
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/webhook"
              required
            />
            <Input
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="Секрет"
            />
            <Input
              value={eventTypes}
              onChange={(e) => setEventTypes(e.target.value)}
              placeholder="Типы событий через запятую"
            />
            <Button type="submit" disabled={loading}>
              Создать
            </Button>
          </form>
          {endpoints.length === 0 ? (
            <EmptyState
              title="Точки вебхуков отсутствуют"
              description="Создайте первую точку, чтобы начать проверку доставки и интеграционных уведомлений."
            />
          ) : (
            <ul className="space-y-1 text-sm">
              {endpoints.map((item) => (
                <li key={item.id}>
                  {item.url} — <b>{item.enabled ? "включено" : "отключено"}</b>{" "}
                  ({item.subscribed_events.join(", ") || "все"})
                  <Button
                    size="sm"
                    // BIZ-60 волна 4: кнопка в ПОВТОРЯЮЩЕЙСЯ строке списка не
                    // может быть главной — её экземпляров столько, сколько
                    // эндпоинтов (ловушка BillingPage: лимит не должен зависеть
                    // от данных). Проверка доставки — вторичное действие.
                    variant="outline"
                    className="ml-2"
                    onClick={() => void runTest(item.id)}
                    disabled={loading}
                  >
                    Тест
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Доставки</CardTitle>
        </CardHeader>
        <CardContent>
          {deliveries.length === 0 ? (
            <EmptyState
              title="История доставок пуста"
              description="После первой отправки вебхука здесь появится история доставок."
            />
          ) : (
            <ul className="space-y-1 text-sm">
              {deliveries.slice(0, 20).map((item) => (
                <li key={item.id}>
                  {item.event_id} → {item.endpoint_id} —{" "}
                  <b>{statusLabel(item.status)}</b> (попыток: {item.attempts})
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Хронология исходящей очереди заданий</CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <EmptyState
              title="Событий исходящей очереди нет"
              description="После первых фоновых событий здесь появится хронология интеграционных сообщений."
            />
          ) : (
            <ul className="space-y-1 text-sm">
              {items.map((item) => (
                <li key={item.id}>
                  {item.event_type} — <b>{statusLabel(item.status)}</b>{" "}
                  (попыток: {item.attempts})
                </li>
              ))}
            </ul>
          )}
          <Button
            // Служебное обновление списка — не главное действие экрана.
            variant="outline"
            className="mt-3"
            onClick={() => void load()}
            disabled={loading}
          >
            Обновить
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default OutboxPage;
