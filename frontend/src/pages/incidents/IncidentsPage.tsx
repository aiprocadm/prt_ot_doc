import { useEffect, useState } from "react";

import { incidentsApi, type Incident } from "@/api/incidents";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";
import { toast } from "sonner";

const INCIDENT_TYPES = ["near_miss", "micro_trauma", "injury", "fatal", "fire", "environmental", "other"];
const SEVERITY_LEVELS = ["low", "medium", "high", "critical"];

const IncidentsPage = () => {
  const [items, setItems] = useState<Incident[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  // create dialog state
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    title: "",
    description: "",
    incident_type: "near_miss",
    occurred_at: new Date().toISOString().slice(0, 16),
    company_id: "",
    site_id: "",
    severity: "medium"
  });

  const load = async (status = statusFilter) => {
    setLoading(true);
    setError(null);
    try {
      const page = await incidentsApi.list({
        limit: 100,
        status_filter: status || undefined
      });
      setItems(page.items);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить инциденты" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load("");
  }, []);

  const handleCreate = async () => {
    if (!form.title || !form.company_id) {
      toast.error("Укажите заголовок и компанию");
      return;
    }
    setCreating(true);
    try {
      await incidentsApi.create({
        title: form.title,
        description: form.description || undefined,
        incident_type: form.incident_type,
        occurred_at: new Date(form.occurred_at).toISOString(),
        company_id: form.company_id,
        site_id: form.site_id || undefined,
        severity: form.severity
      });
      toast.success("Инцидент зарегистрирован");
      setCreateOpen(false);
      setForm({
        title: "",
        description: "",
        incident_type: "near_miss",
        occurred_at: new Date().toISOString().slice(0, 16),
        company_id: "",
        site_id: "",
        severity: "medium"
      });
      void load();
    } catch (err) {
      toast.error((err as ApiError)?.message ?? "Ошибка при создании инцидента");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Инциденты/НС" }]} />
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(event) => {
              const next = event.target.value;
              setStatusFilter(next);
              void load(next);
            }}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            aria-label="Фильтр по статусу"
          >
            <option value="">Все статусы</option>
            <option value="draft">draft</option>
            <option value="investigating">investigating</option>
            <option value="closed">closed</option>
          </select>
          <Button variant="outline" onClick={() => void load()}>Обновить</Button>

          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button>Зарегистрировать инцидент</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Регистрация инцидента / НС</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="inc-title">Заголовок *</Label>
                  <Input
                    id="inc-title"
                    value={form.title}
                    onChange={(e) => setForm((prev) => ({ ...prev, title: e.target.value }))}
                    placeholder="Краткое описание события"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="inc-type">Тип события</Label>
                    <select
                      id="inc-type"
                      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={form.incident_type}
                      onChange={(e) => setForm((prev) => ({ ...prev, incident_type: e.target.value }))}
                    >
                      {INCIDENT_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="inc-severity">Тяжесть</Label>
                    <select
                      id="inc-severity"
                      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={form.severity}
                      onChange={(e) => setForm((prev) => ({ ...prev, severity: e.target.value }))}
                    >
                      {SEVERITY_LEVELS.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="inc-date">Дата/время события *</Label>
                  <Input
                    id="inc-date"
                    type="datetime-local"
                    value={form.occurred_at}
                    onChange={(e) => setForm((prev) => ({ ...prev, occurred_at: e.target.value }))}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="inc-company">ID компании *</Label>
                    <Input
                      id="inc-company"
                      value={form.company_id}
                      onChange={(e) => setForm((prev) => ({ ...prev, company_id: e.target.value }))}
                      placeholder="UUID компании"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="inc-site">ID площадки</Label>
                    <Input
                      id="inc-site"
                      value={form.site_id}
                      onChange={(e) => setForm((prev) => ({ ...prev, site_id: e.target.value }))}
                      placeholder="UUID площадки (опционально)"
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="inc-desc">Описание</Label>
                  <Textarea
                    id="inc-desc"
                    value={form.description}
                    onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
                    placeholder="Подробное описание произошедшего"
                    rows={3}
                  />
                </div>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setCreateOpen(false)}>Отмена</Button>
                  <Button disabled={creating} onClick={() => void handleCreate()}>
                    {creating ? "Сохранение…" : "Зарегистрировать"}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      {loading ? <LoadingScreen label="Загрузка инцидентов" /> : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Инциденты и расследования</CardTitle>
        </CardHeader>
        <CardContent>
          {!loading && items.length === 0 ? (
            <EmptyState title="Инциденты не найдены" description="Снимите фильтр или зарегистрируйте новый инцидент." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Событие</TableHead>
                  <TableHead>Тип</TableHead>
                  <TableHead>Площадка</TableHead>
                  <TableHead>Дата</TableHead>
                  <TableHead>Статус</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((incident) => (
                  <TableRow key={incident.id}>
                    <TableCell className="font-medium">{incident.id}</TableCell>
                    <TableCell>{incident.title}</TableCell>
                    <TableCell>{incident.incident_type}</TableCell>
                    <TableCell>{incident.site_id}</TableCell>
                    <TableCell>{formatDate(incident.occurred_at)}</TableCell>
                    <TableCell>
                      <StatusBadge status={incident.status} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default IncidentsPage;
