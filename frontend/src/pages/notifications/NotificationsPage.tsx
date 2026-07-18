import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useSearchParams } from "react-router-dom";

import { notificationsApi } from "@/api/notifications";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { ApiError } from "@/types/dto/common";

const channels = ["all", "inapp", "email", "telegram", "webhook"] as const;
const priorities = ["all", "low", "medium", "high", "critical"] as const;
const statuses = ["all", "unread", "read", "queued", "sent", "failed"] as const;

type NotificationItem = {
  id: string;
  title: string;
  body: string;
  type: string;
  status: string;
  channel: string;
  priority: string;
  is_read: boolean;
  deeplink?: string | null;
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

type NotificationTemplate = {
  id: string;
  code: string;
  channel: string;
  type: string;
  locale: string;
  title_template?: string | null;
  subject_template?: string | null;
  body_template: string;
  is_active: boolean;
};

const NotificationsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<(typeof statuses)[number]>(
    (statuses.find((item) => item === searchParams.get("status")) ?? "unread") as (typeof statuses)[number]
  );
  const [channel, setChannel] = useState<(typeof channels)[number]>(
    (channels.find((item) => item === searchParams.get("channel")) ?? "all") as (typeof channels)[number]
  );
  const [priority, setPriority] = useState<(typeof priorities)[number]>(
    (priorities.find((item) => item === searchParams.get("priority")) ?? "all") as (typeof priorities)[number]
  );
  const [type, setType] = useState(searchParams.get("type") ?? "");
  const patchQuery = useCallback((patch: { status?: string; channel?: string; priority?: string; type?: string }) => {
    const next = new URLSearchParams(searchParams);
    if ("status" in patch) {
      if (patch.status && patch.status !== "all") next.set("status", patch.status);
      else next.delete("status");
    }
    if ("channel" in patch) {
      if (patch.channel && patch.channel !== "all") next.set("channel", patch.channel);
      else next.delete("channel");
    }
    if ("priority" in patch) {
      if (patch.priority && patch.priority !== "all") next.set("priority", patch.priority);
      else next.delete("priority");
    }
    if ("type" in patch) {
      if (patch.type) next.set("type", patch.type);
      else next.delete("type");
    }
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await notificationsApi.list<NotificationItem>({
        ...(statusFilter !== "all" ? { status: statusFilter } : {}),
        ...(channel !== "all" ? { channel } : {}),
        ...(priority !== "all" ? { priority } : {}),
        ...(type ? { type } : {})
      });
      setItems(response.items);
      setUnreadCount(response.unread_count);
      setSelectedIds([]);
    } catch (err) {
      const apiError = (err as ApiError) ?? { status: 500, message: "Не удалось загрузить уведомления" };
      setError({ status: apiError.status ?? 500, message: apiError.message ?? "Не удалось загрузить уведомления" });
    } finally {
      setLoading(false);
    }
  }, [channel, priority, statusFilter, type]);

  const loadSettings = useCallback(async () => {
    try {
      const response = await notificationsApi.getMySettings<NotificationSettings>();
      setSettings(response);
    } catch {
      setSettings(null);
    }
  }, []);

  const loadTemplates = useCallback(async () => {
    try {
      const response = await notificationsApi.listTemplates<NotificationTemplate>();
      setTemplates(response);
    } catch {
      setTemplates([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadSettings();
    void loadTemplates();
  }, [loadSettings, loadTemplates]);

  const selectedUnreadIds = useMemo(() => items.filter((item) => selectedIds.includes(item.id) && !item.is_read).map((item) => item.id), [items, selectedIds]);
  const groupedByType = useMemo(() => Array.from(new Set(items.map((item) => item.type))).sort(), [items]);

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };

  const markRead = async (ids: string[]) => {
    if (!ids.length) return;
    setError(null);
    try {
      await notificationsApi.markRead(ids);
      await load();
    } catch (err) {
      const apiError = (err as ApiError) ?? { status: 500, message: "Не удалось отметить уведомления как прочитанные" };
      setError({ status: apiError.status ?? 500, message: apiError.message ?? "Не удалось отметить уведомления как прочитанные" });
    }
  };

  const saveSettings = async () => {
    if (!settings) return;
    setError(null);
    try {
      await notificationsApi.saveMySettings(settings);
      await loadSettings();
    } catch (err) {
      const apiError = (err as ApiError) ?? { status: 500, message: "Не удалось сохранить настройки уведомлений" };
      setError({ status: apiError.status ?? 500, message: apiError.message ?? "Не удалось сохранить настройки уведомлений" });
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Центр уведомлений</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <div className="rounded-full border px-3 py-1 text-xs text-muted-foreground">Unread: {unreadCount}</div>
            <Button variant="outline" onClick={() => void markRead(items.filter((item) => !item.is_read).map((item) => item.id))}>
              Отметить все прочитанными
            </Button>
            <Button variant="outline" onClick={() => void markRead(selectedUnreadIds)} disabled={!selectedUnreadIds.length}>
              Отметить выбранные ({selectedUnreadIds.length})
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <ErrorState error={error ?? undefined} onRetry={() => void load()} />
          {loading ? <LoadingScreen label="Загрузка уведомлений" /> : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState title="Уведомления отсутствуют" description="Новые события появятся здесь автоматически." />
          ) : null}
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <select
              className="h-10 rounded-md border px-3"
              value={statusFilter}
              onChange={(event) => {
                const next = event.target.value as (typeof statuses)[number];
                setStatusFilter(next);
                patchQuery({ status: next });
              }}
            >
              {statuses.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select
              className="h-10 rounded-md border px-3"
              value={channel}
              onChange={(event) => {
                const next = event.target.value as (typeof channels)[number];
                setChannel(next);
                patchQuery({ channel: next });
              }}
            >
              {channels.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <select
              className="h-10 rounded-md border px-3"
              value={priority}
              onChange={(event) => {
                const next = event.target.value as (typeof priorities)[number];
                setPriority(next);
                patchQuery({ priority: next });
              }}
            >
              {priorities.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
            <Input
              placeholder="Тип уведомления"
              value={type}
              onChange={(event) => {
                const next = event.target.value;
                setType(next);
                patchQuery({ type: next });
              }}
            />
            <div className="rounded-md border px-3 py-2 text-sm text-muted-foreground">Типы: {groupedByType.join(", ") || "—"}</div>
          </div>
          {!loading ? items.map((item) => (
            <div key={item.id} className={`rounded-md border p-3 ${item.is_read ? "bg-muted/30" : "border-primary/40"}`}>
              <div className="flex items-start gap-3">
                <input type="checkbox" className="mt-1" checked={selectedIds.includes(item.id)} onChange={() => toggleSelected(item.id)} aria-label={`Выбрать уведомление ${item.id}`} />
                <div className="flex-1">
                  <div className="flex flex-wrap items-start justify-between gap-3">
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
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded-full border px-2 py-1">{item.type}</span>
                    <span className="rounded-full border px-2 py-1">{item.is_read ? "прочитано" : "непрочитано"}</span>
                    {!item.is_read ? <Button size="sm" variant="ghost" onClick={() => void markRead([item.id])}>Пометить прочитанным</Button> : null}
                    {item.deeplink || item.payload?.deeplink ? (
                      <Link className="text-primary underline" to={item.deeplink ?? item.payload?.deeplink ?? "#"}>
                        Открыть связанную сущность
                      </Link>
                    ) : null}
                  </div>
                </div>
              </div>
            </div>
          )) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Предпочтения и тихие часы</CardTitle></CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(settings?.email_enabled)} onChange={(e) => setSettings((prev) => (prev ? { ...prev, email_enabled: e.target.checked } : prev))} /> Электронная почта</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(settings?.telegram_enabled)} onChange={(e) => setSettings((prev) => (prev ? { ...prev, telegram_enabled: e.target.checked } : prev))} /> Телеграм</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(settings?.inapp_enabled)} onChange={(e) => setSettings((prev) => (prev ? { ...prev, inapp_enabled: e.target.checked } : prev))} /> В приложении</label>
          <Input placeholder="Режим дайджеста: off / daily / weekly" value={settings?.digest_mode ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, digest_mode: e.target.value } : prev))} />
          <Input placeholder="Адрес электронной почты" value={settings?.email ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, email: e.target.value } : prev))} />
          <Input placeholder="ID чата Телеграм" value={settings?.telegram_chat_id ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, telegram_chat_id: e.target.value } : prev))} />
          <Input placeholder="Тихие часы: с (например 22:00)" value={settings?.quiet_hours?.from ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, quiet_hours: { ...(prev.quiet_hours ?? {}), from: e.target.value } } : prev))} />
          <Input placeholder="Тихие часы: до (например 08:00)" value={settings?.quiet_hours?.to ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, quiet_hours: { ...(prev.quiet_hours ?? {}), to: e.target.value } } : prev))} />
          <Input placeholder="Часовой пояс (Europe/Moscow)" value={settings?.quiet_hours?.tz ?? ""} onChange={(e) => setSettings((prev) => (prev ? { ...prev, quiet_hours: { ...(prev.quiet_hours ?? {}), tz: e.target.value } } : prev))} />
          <Button className="md:col-span-2" onClick={() => void saveSettings()}>Сохранить настройки</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Шаблоны уведомлений</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {templates.length ? templates.map((template) => (
            <div key={template.id} className="rounded border p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-medium">{template.code}</div>
                  <div className="text-xs text-muted-foreground">{template.type} · {template.channel} · {template.locale}</div>
                </div>
                <div className="rounded-full border px-2 py-1 text-xs">{template.is_active ? "активен" : "отключён"}</div>
              </div>
              <div className="mt-2 text-sm text-muted-foreground">{template.title_template ?? template.subject_template ?? "Без заголовка"}</div>
              <div className="mt-1 text-xs text-muted-foreground line-clamp-2">{template.body_template}</div>
            </div>
          )) : <div className="text-sm text-muted-foreground">Шаблоны пока не настроены — база для шаблонов в области тенанта готова.</div>}
        </CardContent>
      </Card>
    </div>
  );
};

export default NotificationsPage;
