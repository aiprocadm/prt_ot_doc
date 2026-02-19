import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type OutboxItem = { id: string; event_type: string; status: string; attempts: number };

const OutboxPage = () => {
  const [items, setItems] = useState<OutboxItem[]>([]);

  useEffect(() => {
    apiClient.get<{ items: OutboxItem[] }>("/admin/outbox").then((response) => setItems(response.data.items ?? []));
  }, []);

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Outbox" }]} />
      <Card>
        <CardHeader>
          <CardTitle>Outbox events inspector</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1 text-sm">
            {items.map((item) => (
              <li key={item.id}>
                {item.event_type} — <b>{item.status}</b> (attempts: {item.attempts})
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
};

export default OutboxPage;
