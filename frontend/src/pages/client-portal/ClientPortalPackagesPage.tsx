import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/common/StatusBadge";
import { formatDate } from "@/utils/datetime";

type PortalRun = { id: string; status: string; client_company_id?: string | null; started_at?: string | null; finished_at?: string | null; };
type PortalDetail = { run: PortalRun; history: { status_flow: string[]; events_count: number; tickets_count: number; requirements_total: number; requirements_missing: number; }; files: Array<{ kind: string; signed_url?: string; sha256?: string; size?: number | null; }>; events: Array<{ id: string; type: string; created_at: string; }>; tickets: Array<{ id: string; title: string; status: string; created_at: string; }>; };

const ClientPortalPackagesPage = () => {
  const [items, setItems] = useState<PortalRun[]>([]);
  const [selected, setSelected] = useState<PortalDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get<PortalRun[]>("/client-portal/packages");
      setItems(data);
      if (data[0]) {
        const detail = await apiClient.get<PortalDetail>(`/client-portal/packages/${data[0].id}`);
        setSelected(detail.data);
      } else {
        setSelected(null);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Кабинет клиента" }, { label: "Пакеты" }]} />
        <Button variant="outline" onClick={() => void load()} disabled={loading}>Обновить</Button>
      </div>
      <div className="grid gap-6 xl:grid-cols-[1.1fr_1.4fr]">
        <Card>
          <CardHeader><CardTitle>Список пакетов</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {items.map((item) => (
              <button key={item.id} className="w-full rounded-lg border p-3 text-left hover:bg-muted" onClick={() => void apiClient.get<PortalDetail>(`/client-portal/packages/${item.id}`).then((detail) => setSelected(detail.data))}>
                <div className="flex items-center justify-between gap-2"><div className="font-medium">{item.id}</div><StatusBadge status={item.status} /></div>
                <div className="mt-1 text-sm text-muted-foreground">Запуск: {item.started_at ? formatDate(item.started_at) : "—"}</div>
              </button>
            ))}
            {!items.length ? <div className="text-sm text-muted-foreground">Пакеты пока не найдены.</div> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Детали пакета</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {!selected ? <div className="text-sm text-muted-foreground">Выберите пакет слева.</div> : (
              <>
                <div className="flex items-center justify-between"><div className="font-medium">{selected.run.id}</div><StatusBadge status={selected.run.status} /></div>
                <div className="grid gap-3 md:grid-cols-4">
                  <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">События</div><div className="text-xl font-semibold">{selected.history.events_count}</div></div>
                  <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Запросы</div><div className="text-xl font-semibold">{selected.history.tickets_count}</div></div>
                  <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Требования</div><div className="text-xl font-semibold">{selected.history.requirements_total}</div></div>
                  <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Не закрыто</div><div className="text-xl font-semibold text-destructive">{selected.history.requirements_missing}</div></div>
                </div>
                <div>
                  <div className="mb-2 text-sm font-medium">Файлы</div>
                  <div className="space-y-2">{selected.files.map((file) => <div key={`${file.kind}-${file.sha256}`} className="rounded border p-3 text-sm"><div className="font-medium">{file.kind}</div><div className="text-muted-foreground">SHA256: {file.sha256 ?? "—"} · Размер: {file.size ?? "—"}</div>{file.signed_url ? <a className="text-primary underline" href={file.signed_url}>Скачать</a> : null}</div>)}</div>
                </div>
                <div>
                  <div className="mb-2 text-sm font-medium">Timeline</div>
                  <div className="flex flex-wrap gap-2">{selected.history.status_flow.map((status) => <StatusBadge key={status} status={status} />)}</div>
                  <div className="mt-3 space-y-2">{selected.events.map((event) => <div key={event.id} className="rounded border p-3 text-sm">{event.type} · {formatDate(event.created_at)}</div>)}</div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default ClientPortalPackagesPage;
