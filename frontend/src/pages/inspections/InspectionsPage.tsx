import { useEffect, useState } from "react";

import { inspectionsApi, type Inspection } from "@/api/inspections";
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
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";
import { toast } from "sonner";

const INSPECTION_TYPES = ["planned", "unplanned", "documentary", "on_site", "counter"];

const InspectionsPage = () => {
  const [items, setItems] = useState<Inspection[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  // create dialog state
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    company_id: "",
    site_id: "",
    inspection_type: "planned",
    authority: "",
    purpose: "",
    scheduled_at: new Date().toISOString().slice(0, 10)
  });

  const load = async (status = statusFilter) => {
    setLoading(true);
    setError(null);
    try {
      const page = await inspectionsApi.list({
        limit: 100,
        status_filter: status || undefined
      });
      setItems(page.items);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить проверки" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load("");
  }, []);

  const handleCreate = async () => {
    if (!form.company_id || !form.authority) {
      toast.error("Укажите компанию и проверяющий орган");
      return;
    }
    setCreating(true);
    try {
      await inspectionsApi.create({
        company_id: form.company_id,
        site_id: form.site_id || undefined,
        inspection_type: form.inspection_type,
        authority: form.authority,
        purpose: form.purpose || undefined,
        scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : undefined
      });
      toast.success("Проверка создана");
      setCreateOpen(false);
      setForm({
        company_id: "",
        site_id: "",
        inspection_type: "planned",
        authority: "",
        purpose: "",
        scheduled_at: new Date().toISOString().slice(0, 10)
      });
      void load();
    } catch (err) {
      toast.error((err as ApiError)?.message ?? "Ошибка при создании проверки");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Проверки/предписания" }]} />
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(event) => {
              const next = event.target.value;
              setStatusFilter(next);
              void load(next);
            }}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            aria-label="Фильтр по статусу проверки"
          >
            <option value="">Все статусы</option>
            <option value="planned">planned</option>
            <option value="in_progress">in_progress</option>
            <option value="completed">completed</option>
          </select>
          <Button variant="outline" onClick={() => void load()}>Обновить</Button>

          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button>Создать проверку</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Создание проверки / предписания</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="insp-company">ID компании *</Label>
                    <Input
                      id="insp-company"
                      value={form.company_id}
                      onChange={(e) => setForm((prev) => ({ ...prev, company_id: e.target.value }))}
                      placeholder="UUID компании"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="insp-site">ID площадки</Label>
                    <Input
                      id="insp-site"
                      value={form.site_id}
                      onChange={(e) => setForm((prev) => ({ ...prev, site_id: e.target.value }))}
                      placeholder="Опционально"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="insp-type">Тип проверки</Label>
                    <select
                      id="insp-type"
                      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={form.inspection_type}
                      onChange={(e) => setForm((prev) => ({ ...prev, inspection_type: e.target.value }))}
                    >
                      {INSPECTION_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="insp-date">Плановая дата</Label>
                    <Input
                      id="insp-date"
                      type="date"
                      value={form.scheduled_at}
                      onChange={(e) => setForm((prev) => ({ ...prev, scheduled_at: e.target.value }))}
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="insp-authority">Проверяющий орган *</Label>
                  <Input
                    id="insp-authority"
                    value={form.authority}
                    onChange={(e) => setForm((prev) => ({ ...prev, authority: e.target.value }))}
                    placeholder="Ростехнадзор, Роструд, МЧС…"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="insp-purpose">Цель проверки</Label>
                  <Input
                    id="insp-purpose"
                    value={form.purpose}
                    onChange={(e) => setForm((prev) => ({ ...prev, purpose: e.target.value }))}
                    placeholder="Контроль соблюдения требований ОТ"
                  />
                </div>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setCreateOpen(false)}>Отмена</Button>
                  <Button disabled={creating} onClick={() => void handleCreate()}>
                    {creating ? "Создание…" : "Создать проверку"}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      {loading ? <LoadingScreen label="Загрузка проверок" /> : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">План проверок и предписаний</CardTitle>
        </CardHeader>
        <CardContent>
          {!loading && items.length === 0 ? (
            <EmptyState title="Проверки не найдены" description="Измените фильтры или создайте новую проверку." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Тип</TableHead>
                  <TableHead>Площадка</TableHead>
                  <TableHead>Орган</TableHead>
                  <TableHead>Срок</TableHead>
                  <TableHead>Статус</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((inspection) => (
                  <TableRow key={inspection.id}>
                    <TableCell className="font-medium">{inspection.id}</TableCell>
                    <TableCell>{inspection.inspection_type}</TableCell>
                    <TableCell>{inspection.site_id ?? "—"}</TableCell>
                    <TableCell>{inspection.authority}</TableCell>
                    <TableCell>{inspection.scheduled_at ? formatDate(inspection.scheduled_at) : "—"}</TableCell>
                    <TableCell>
                      <StatusBadge status={inspection.status} />
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

export default InspectionsPage;
