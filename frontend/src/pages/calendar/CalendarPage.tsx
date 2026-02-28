import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type CalendarEvent = {
  id: string;
  source: string;
  entity_type: string;
  entity_id: string;
  title: string;
  date: string;
  status?: string | null;
  deeplink?: string | null;
};

const CalendarPage = () => {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [mode, setMode] = useState<"month" | "week" | "list">("list");
  const [source, setSource] = useState("all");

  useEffect(() => {
    const load = async () => {
      const response = await apiClient.get<CalendarEvent[]>("/notifications/calendar/events", {
        params: source === "all" ? undefined : { source }
      });
      setEvents(response.data);
    };
    void load();
  }, [source]);

  const grouped = useMemo(() => {
    if (mode === "list") return [{ label: "Список", items: events }];
    const buckets = new Map<string, CalendarEvent[]>();
    for (const event of events) {
      const date = new Date(event.date);
      const key = mode === "week" ? `${date.getUTCFullYear()}-W${Math.ceil(date.getUTCDate() / 7)}` : `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
      const list = buckets.get(key) ?? [];
      list.push(event);
      buckets.set(key, list);
    }
    return [...buckets.entries()].map(([label, items]) => ({ label, items }));
  }, [events, mode]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>Календарь мероприятий</CardTitle>
        <div className="flex flex-wrap gap-2">
          <Button variant={mode === "month" ? "default" : "outline"} onClick={() => setMode("month")}>Month</Button>
          <Button variant={mode === "week" ? "default" : "outline"} onClick={() => setMode("week")}>Week</Button>
          <Button variant={mode === "list" ? "default" : "outline"} onClick={() => setMode("list")}>List</Button>
          <Button variant={source === "all" ? "default" : "outline"} onClick={() => setSource("all")}>Все</Button>
          <Button variant={source === "training" ? "default" : "outline"} onClick={() => setSource("training")}>Обучение</Button>
          <Button variant={source === "ppe" ? "default" : "outline"} onClick={() => setSource("ppe")}>СИЗ</Button>
          <Button variant={source === "inspection" ? "default" : "outline"} onClick={() => setSource("inspection")}>Проверки</Button>
          <Button variant={source === "task" ? "default" : "outline"} onClick={() => setSource("task")}>Задачи</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {grouped.map((group) => (
          <div key={group.label} className="space-y-2">
            <div className="text-sm font-semibold text-muted-foreground">{group.label}</div>
            {group.items.map((event) => (
              <div key={event.id} className="rounded border p-3">
                <div className="font-medium">{event.title}</div>
                <div className="text-sm text-muted-foreground">{new Date(event.date).toLocaleString()} · {event.source} · {event.status ?? "active"}</div>
                {event.deeplink ? <a className="text-sm text-primary underline" href={event.deeplink}>Открыть карточку</a> : null}
              </div>
            ))}
          </div>
        ))}
      </CardContent>
    </Card>
  );
};

export default CalendarPage;
