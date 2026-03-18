import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const channels = ["all", "inapp", "email", "telegram", "webhook"] as const;
const priorities = ["all", "low", "medium", "high", "critical"] as const;

type NotificationItem = {
  id: string;
  title: string;
  body: string;
  type: string;
  status: string;
  channel: string;
  priority: string;
  payload?: { deeplink?: string };
};

type NotificationSettings = {
  email_enabled: boolean;
  telegram_enabled: boolean;
  inapp_enabled: boolean;
  email?: string | null;
  telegram_chat_id?: string | null;
  quiet_hours?: { from?: string; to?: string; tz?: string } | null;
  digest_mode?: string | null;
};

const NotificationsPage = () => {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [filter, setFilter] = useState<"all" | "unread">("unread");
  const [channel, setChannel] = useState<(typeof channels)[number]>("all");
  const [priority, setPriority] = useState<(typeof priorities)[number]>("all");
  const [type, setType] = useState("");
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);

  const load = async () => {
    const response = await apiClient.get<{ items: NotificationItem[]; unread_count: number }>("/notifications", {
      params: {
        ...(filter === "unread" ? { status: "unread" } : {}),
        ...(channel !== "all" ? { channel } : {}),
        ...(priority !== "all" ? { priority } : {}),
        ...(type ? { type } : {})
      }
    });
    setItems(response.data.items);
    setUnreadCount(response.data.unread_count);
  };

  const loadSettings = async () => {
    const response = await apiClient.get<NotificationSettings>("/notifications/settings/me");
    setSettings(response.data);
  };

  useEffect(() => {
    void load();
  }, [filter, channel, priority, type]);

  useEffect(() => {
    void loadSettings();
  }, []);

  const markAllRead = async () => {
    await apiClient.post("/notifications/mark-read", { ids: items.map((item) => item.id) });
    await load();
  };

  const saveSettings = async () => {
    if (!settings) return;
    await apiClient.put("/notifications/settings/me", settings);
    await loadSettings();
  };

  const groupedByType = useMemo(() => Array.from(new Set(items.map((item) => item.type))).sort(), [items]);

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
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-4">
            <select className="h-10 rounded-md border px-3" value={channel} onChange={(event) => setChannel(event.target.value as (typeof channels)[number])}>
              {channels.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select className="h-10 rounded-md border px-3" value={priority} onChange={(event) => setPriority(event.target.value as (typeof priorities)[number])}>
              {priorities.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <Input placeholder="Тип уведомления" value={type} onChange={(event) => setType(event.target.value)} />
            <div className="rounded-md border px-3 py-2 text-sm text-muted-foreground">Типы в выборке: {groupedByType.join(", ") || "—"}</div>
          </div>
          {items.map((item) => (
            <div key={item.id} className="rounded-md border p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium">{item.title}</div>
                  <div className="text-sm text-muted-foreground">{item.body}</div>
                </div>
                <div className="text-right text-xs text-muted-foreground">
                  <div>{item.channel}</div>
                  <div>{item.priority}</div>
                  <div>{item.status}</div>
                </div>
              </div>
              <div className="mt-2 text-xs">Тип: {item.type}</div>
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
        <CardHeader><CardTitle>Предпочтения и quiet hours</CardTitle></CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(settings?.email_enabled)} onChange={(e) => setSettings((prev) => (prev ? { ...prev, email_enabled: e.target.checked } : prev))} /> Email</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(settings?.telegram_enabled)} onChange={(e) => setSettings((prev) => (prev ? { ...prev, telegram_enabled: e.target.checked } : prev))} /> Telegram</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(settings?.inapp_enabled)} onChange={(e) => setSettings((prev) => (prev ? { ...prev, inapp_enabled: e.target.checked } : prev))} /> In-app</label>
          <Input placeholder="Digest mode (off/daily/weekly)" value={settings?.digest_mode ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, digest_mode: e.target.value } : prev))} />
          <Input placeholder="Email" value={settings?.email ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, email: e.target.value } : prev))} />
          <Input placeholder="Telegram chat id" value={settings?.telegram_chat_id ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, telegram_chat_id: e.target.value } : prev))} />
          <Input placeholder="Quiet hours from (22:00)" value={settings?.quiet_hours?.from ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, quiet_hours: { ...(prev.quiet_hours ?? {}), from: e.target.value } } : prev))} />
          <Input placeholder="Quiet hours to (08:00)" value={settings?.quiet_hours?.to ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, quiet_hours: { ...(prev.quiet_hours ?? {}), to: e.target.value } } : prev))} />
          <Input placeholder="Timezone (Europe/Moscow)" value={settings?.quiet_hours?.tz ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, quiet_hours: { ...(prev.quiet_hours ?? {}), tz: e.target.value } } : prev))} />
          <Button className="md:col-span-2" onClick={() => void saveSettings()}>Сохранить настройки</Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default NotificationsPage;
