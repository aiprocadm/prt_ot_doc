import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type OutboxItem = { id: string; event_type: string; status: string; attempts: number };
type Endpoint = { id: string; url: string; enabled: boolean; subscribed_events: string[] };
type Delivery = { id: string; endpoint_id: string; event_id: string; status: string; attempts: number };

const OutboxPage = () => {
  const [items, setItems] = useState<OutboxItem[]>([]);
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);

  const load = async () => {
    const [outbox, eps, dels] = await Promise.all([
      apiClient.get<{ items: OutboxItem[] }>("/admin/outbox"),
      apiClient.get<Endpoint[]>("/webhooks/endpoints"),
      apiClient.get<Delivery[]>("/webhooks/deliveries"),
    ]);
    setItems(outbox.data.items ?? []);
    setEndpoints(eps.data ?? []);
    setDeliveries(dels.data ?? []);
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Integrations / Webhooks" }]} />
      <Card>
        <CardHeader>
          <CardTitle>Webhook subscriptions</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1 text-sm">
            {endpoints.map((item) => (
              <li key={item.id}>
                {item.url} — <b>{item.enabled ? "enabled" : "disabled"}</b> ({item.subscribed_events.join(", ") || "all"})
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Deliveries</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1 text-sm">
            {deliveries.slice(0, 20).map((item) => (
              <li key={item.id}>
                {item.event_id} → {item.endpoint_id} — <b>{item.status}</b> (attempts: {item.attempts})
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Job outbox timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1 text-sm">
            {items.map((item) => (
              <li key={item.id}>
                {item.event_type} — <b>{item.status}</b> (attempts: {item.attempts})
              </li>
            ))}
          </ul>
          <Button className="mt-3" onClick={() => load()}>
            Test / Refresh
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default OutboxPage;
