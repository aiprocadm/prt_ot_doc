import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type NotificationItem = {
  id: string;
  title: string;
  body: string;
  status: string;
  payload?: { deeplink?: string };
};

type NotificationSettings = {
  email_enabled: boolean;
  telegram_enabled: boolean;
  inapp_enabled: boolean;
  email?: string | null;
  telegram_chat_id?: string | null;
  quiet_hours?: { from?: string; to?: string; tz?: string } | null;
};

const NotificationsPage = () => {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [filter, setFilter] = useState<"all" | "unread">("unread");
  const [settings, setSettings] = useState<NotificationSettings | null>(null);

  const load = async () => {
    const response = await apiClient.get<{ items: NotificationItem[] }>("/notifications", {
      params: filter === "unread" ? { status: "unread" } : undefined
    });
    setItems(response.data.items);
  };

  const loadSettings = async () => {
    const response = await apiClient.get<NotificationSettings>("/notifications/settings/me");
    setSettings(response.data);
  };

  useEffect(() => {
    void load();
  }, [filter]);

  useEffect(() => {
    void loadSettings();
  }, []);

  const markAllRead = async () => {
    await apiClient.post("/notifications/mark-read", { ids: items.map((item) => item.id) });
    await load();
  };

  const unreadCount = useMemo(() => items.filter((item) => item.status !== "read").length, [items]);

  const saveSettings = async () => {
    if (!settings) return;
    await apiClient.put("/notifications/settings/me", settings);
    await loadSettings();
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Центр уведомлений</CardTitle>
          <div className="flex items-center gap-2">
            <Button variant={filter === "unread" ? "default" : "outline"} onClick={() => setFilter("unread")}>Непрочитанные</Button>
            <Button variant={filter === "all" ? "default" : "outline"} onClick={() => setFilter("all")}>Все</Button>
            <Button variant="outline" onClick={() => void markAllRead()}>
              Отметить прочитанными ({unreadCount})
            </Button>
          </div>
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

      <Card>
        <CardHeader>
          <CardTitle>Мои уведомления</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(settings?.email_enabled)} onChange={(e) => setSettings((prev) => (prev ? { ...prev, email_enabled: e.target.checked } : prev))} /> Email</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(settings?.telegram_enabled)} onChange={(e) => setSettings((prev) => (prev ? { ...prev, telegram_enabled: e.target.checked } : prev))} /> Telegram</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(settings?.inapp_enabled)} onChange={(e) => setSettings((prev) => (prev ? { ...prev, inapp_enabled: e.target.checked } : prev))} /> In-app</label>
          <Input placeholder="Email" value={settings?.email ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, email: e.target.value } : prev))} />
          <Input placeholder="Telegram chat id" value={settings?.telegram_chat_id ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, telegram_chat_id: e.target.value } : prev))} />
          <Input placeholder="Quiet hours from (22:00)" value={settings?.quiet_hours?.from ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, quiet_hours: { ...(prev.quiet_hours ?? {}), from: e.target.value } } : prev))} />
          <Input placeholder="Quiet hours to (08:00)" value={settings?.quiet_hours?.to ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, quiet_hours: { ...(prev.quiet_hours ?? {}), to: e.target.value } } : prev))} />
          <Input placeholder="Timezone (Europe/Berlin)" value={settings?.quiet_hours?.tz ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, quiet_hours: { ...(prev.quiet_hours ?? {}), tz: e.target.value } } : prev))} />
          <Button className="md:col-span-2" onClick={() => void saveSettings()}>Сохранить настройки</Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default NotificationsPage;
