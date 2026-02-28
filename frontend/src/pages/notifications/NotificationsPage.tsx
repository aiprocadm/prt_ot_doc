import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type NotificationItem = {
  id: string;
  title: string;
  body: string;
  status: string;
  payload?: { deeplink?: string };
};

const NotificationsPage = () => {
  const [items, setItems] = useState<NotificationItem[]>([]);

  const load = async () => {
    const response = await apiClient.get<{ items: NotificationItem[] }>("/notifications");
    setItems(response.data.items);
  };

  useEffect(() => {
    void load();
  }, []);

  const markAllRead = async () => {
    await apiClient.post("/notifications/mark-read", { ids: items.map((item) => item.id) });
    await load();
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Центр уведомлений</CardTitle>
          <Button variant="outline" onClick={() => void markAllRead()}>
            Отметить прочитанными
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {items.map((item) => (
            <div key={item.id} className="rounded-md border p-3">
              <div className="font-medium">{item.title}</div>
              <div className="text-sm text-muted-foreground">{item.body}</div>
              <div className="mt-2 text-xs">Статус: {item.status}</div>
              {item.payload?.deeplink ? (
                <Link className="mt-2 inline-block text-sm text-primary underline" to={item.payload.deeplink}>
                  Открыть связанную сущность
                </Link>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
};

export default NotificationsPage;
