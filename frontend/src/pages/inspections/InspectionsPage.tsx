import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { inspectionsApi, type Inspection, type InspectionResult } from "@/api/inspections";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";
import { toast } from "sonner";
import { useCompaniesStore } from "@/stores/companies";
import { entityCardLink } from "@/utils/workspaceNavigation";

const INSPECTION_TYPES = ["planned", "unplanned", "documentary", "on_site", "counter"];

const InspectionsPage = () => {
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState<Inspection[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const { items: companies, list: listCompanies } = useCompaniesStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [focusResults, setFocusResults] = useState<InspectionResult[]>([]);
  const focusedEntityType = searchParams.get("entity_type") ?? undefined;
  const focusedEntityId = searchParams.get("entity_id") ?? undefined;
  const focusedView = searchParams.get("view") === "timeline" ? "timeline" : "summary";

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
    listCompanies({ page_size: 100 }).catch(() => undefined);
  }, [listCompanies]);

  useEffect(() => {
    if (focusedEntityType !== "inspection" || !focusedEntityId) {
      setFocusResults([]);
      return;
    }
    inspectionsApi.listResults(focusedEntityId).then(setFocusResults).catch(() => setFocusResults([]));
  }, [focusedEntityId, focusedEntityType]);

  const focusedInspection = focusedEntityType === "inspection" && focusedEntityId
    ? items.find((inspection) => inspection.id === focusedEntityId) ?? null
    : null;
  const focusSummaryLink = entityCardLink(focusedEntityType, focusedEntityId, "summary");
  const focusTimelineLink = entityCardLink(focusedEntityType, focusedEntityId, "timeline");

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

          <Can
            permission={PERMISSIONS.INSPECTION_CREATE}
            fallback={<Button disabled title="Недостаточно прав для создания проверки">Создать проверку</Button>}
          >
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
                      <Label htmlFor="insp-company">Компания *</Label>
                      <select
                        id="insp-company"
                        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                        value={form.company_id}
                        onChange={(e) => setForm((prev) => ({ ...prev, company_id: e.target.value }))}
                      >
                        <option value="">Выберите компанию</option>
                        {companies.map((company) => (
                          <option key={company.id} value={company.id}>{company.name}</option>
                        ))}
                      </select>
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
          </Can>
        </div>
      </div>

      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      {focusedEntityId && focusedEntityType === "inspection" ? (
        <Card>
          <CardContent className="py-4" data-testid="inspection-focus-card">
            <div className="text-sm font-semibold">Фокус проверки из рабочего пространства</div>
            <p className="mt-1 text-xs text-muted-foreground">
              {focusedInspection
                ? `${focusedInspection.inspection_type} · ${focusedInspection.status} · ${focusedInspection.authority}`
                : `Проверка ${focusedEntityId.slice(0, 8)} загружается...`}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {focusSummaryLink ? (
                <Button size="sm" variant={focusedView === "summary" ? "default" : "outline"} asChild>
                  <Link to={focusSummaryLink}>Сводка</Link>
                </Button>
              ) : null}
              {focusTimelineLink ? (
                <Button size="sm" variant={focusedView === "timeline" ? "default" : "outline"} asChild>
                  <Link to={focusTimelineLink}>Хронология</Link>
                </Button>
              ) : null}
              <Button size="sm" variant="ghost" asChild>
                <Link to="/inspections">Сбросить фокус</Link>
              </Button>
            </div>
            {focusedView === "timeline" ? (
              <div className="mt-3 space-y-2">
                {focusResults.length ? (
                  focusResults.slice(0, 6).map((result) => (
                    <div key={result.id} className="rounded-md border p-2 text-xs">
                      <div className="font-medium">{result.title}</div>
                      <div className="text-muted-foreground">
                        {result.outcome ?? "без outcome"} · {result.issued_at ? formatDate(result.issued_at) : "дата не задана"}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">События timeline пока отсутствуют.</p>
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
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
