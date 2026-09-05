import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  incidentsApi,
  type Incident,
  INCIDENT_STATUS_LABELS,
  OPEN_STATUS_FILTER,
  UNMARKED_DISCIPLINE_FILTER,
} from "@/api/incidents";
import { TRAINING_DISCIPLINE_TITLES } from "@/api/training";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";
import { toast } from "sonner";
import { useCompaniesStore } from "@/stores/companies";

const INCIDENT_TYPES = [
  "near_miss",
  "micro_trauma",
  "injury",
  "fatal",
  "fire",
  "environmental",
  "other",
];
const SEVERITY_LEVELS = ["low", "medium", "high", "critical"];
const INCIDENT_TYPE_LABELS: Record<string, string> = {
  near_miss: "Почти-несчастный случай",
  micro_trauma: "Микротравма",
  injury: "Травма",
  fatal: "Смертельный случай",
  fire: "Пожар",
  environmental: "Экологический инцидент",
  other: "Прочее",
};
const SEVERITY_LABELS: Record<string, string> = {
  low: "Низкая",
  medium: "Средняя",
  high: "Высокая",
  critical: "Критическая",
};

const IncidentsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState<Incident[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>(
    searchParams.get("status") ?? "",
  );
  // Дисциплина живёт в адресе (?discipline=), как и статус: ссылку с
  // контура можно передать — откроется уже отфильтрованный список.
  const [disciplineFilter, setDisciplineFilter] = useState<string>(
    searchParams.get("discipline") ?? "",
  );
  // Компания — тоже в адресе (?company_id=): карточка клиента у аутсорсера
  // ведёт сюда «происшествия этого клиента по этой дисциплине» (срез-61).
  const [companyFilter, setCompanyFilter] = useState<string>(
    searchParams.get("company_id") ?? "",
  );
  const { items: companies, list: listCompanies } = useCompaniesStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const focusedEntityType = searchParams.get("entity_type") ?? undefined;
  const focusedEntityId = searchParams.get("entity_id") ?? undefined;
  const focusedIncident =
    focusedEntityType === "incident" && focusedEntityId
      ? (items.find((incident) => incident.id === focusedEntityId) ?? null)
      : null;

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
    severity: "medium",
    discipline: "",
  });

  const load = useCallback(
    async (
      status = statusFilter,
      discipline = disciplineFilter,
      company = companyFilter,
    ) => {
      setLoading(true);
      setError(null);
      try {
        const page = await incidentsApi.list({
          limit: 100,
          status_filter: status || undefined,
          // фильтрует сервер, а не страница: пустое — ключ не уходит вовсе
          ...(discipline ? { discipline } : {}),
          ...(company ? { company_id: company } : {}),
        });
        setItems(page.items);
      } catch (err) {
        setError(
          (err as ApiError) ?? { message: "Не удалось загрузить инциденты" },
        );
      } finally {
        setLoading(false);
      }
    },
    [statusFilter, disciplineFilter, companyFilter],
  );

  useEffect(() => {
    void load(statusFilter, disciplineFilter, companyFilter);
    listCompanies({ page_size: 100 }).catch(() => undefined);
  }, [listCompanies, load, statusFilter, disciplineFilter, companyFilter]);

  const handleCreate = async () => {
    if (!form.title || !form.company_id) {
      toast.error("Укажите заголовок и компанию");
      return;
    }
    setCreating(true);
    try {
      const created = await incidentsApi.create({
        title: form.title,
        description: form.description || undefined,
        incident_type: form.incident_type,
        occurred_at: new Date(form.occurred_at).toISOString(),
        company_id: form.company_id,
        site_id: form.site_id || undefined,
        severity: form.severity,
        // пусто — «не размечено»: сервер хранит null, а не «охрана труда»
        discipline: form.discipline || null,
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
        severity: "medium",
        discipline: "",
      });
      const params = new URLSearchParams(searchParams);
      params.set("entity_type", "incident");
      params.set("entity_id", created.id);
      setSearchParams(params, { replace: true });
      void load();
    } catch (err) {
      toast.error(
        (err as ApiError)?.message ?? "Ошибка при создании инцидента",
      );
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb
          items={[
            { label: "Главная", to: "/dashboard" },
            { label: "Инциденты/НС" },
          ]}
        />
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(event) => {
              const next = event.target.value;
              setStatusFilter(next);
              const params = new URLSearchParams(searchParams);
              if (next) params.set("status", next);
              else params.delete("status");
              setSearchParams(params, { replace: true });
              void load(next);
            }}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            aria-label="Фильтр по статусу"
          >
            <option value="">Все статусы</option>
            <option value={OPEN_STATUS_FILTER}>Открытые</option>
            {Object.entries(INCIDENT_STATUS_LABELS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
          <select
            value={disciplineFilter}
            onChange={(event) => {
              const next = event.target.value;
              setDisciplineFilter(next);
              const params = new URLSearchParams(searchParams);
              if (next) params.set("discipline", next);
              else params.delete("discipline");
              setSearchParams(params, { replace: true });
              void load(statusFilter, next);
            }}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            aria-label="Фильтр по дисциплине"
          >
            <option value="">Все дисциплины</option>
            {/* «none» — слово фильтра сервера (срез-65): только неразмеченные;
                сюда ведут ссылки «без разметки» из отчётов и разреза */}
            <option value={UNMARKED_DISCIPLINE_FILTER}>Без разметки</option>
            {Object.entries(TRAINING_DISCIPLINE_TITLES).map(([code, title]) => (
              <option key={code} value={code}>
                {title}
              </option>
            ))}
          </select>
          <select
            value={companyFilter}
            onChange={(event) => {
              const next = event.target.value;
              setCompanyFilter(next);
              const params = new URLSearchParams(searchParams);
              if (next) params.set("company_id", next);
              else params.delete("company_id");
              setSearchParams(params, { replace: true });
              void load(statusFilter, disciplineFilter, next);
            }}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            aria-label="Фильтр по компании"
          >
            <option value="">Все компании</option>
            {companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.name}
              </option>
            ))}
            {/* Компания из ссылки, которой нет в первой сотне справочника:
                фильтр всё равно действует, и выбор не должен выглядеть пустым. */}
            {companyFilter &&
            !companies.some((company) => company.id === companyFilter) ? (
              <option value={companyFilter}>Компания из ссылки</option>
            ) : null}
          </select>
          <Button variant="outline" onClick={() => void load()}>
            Обновить
          </Button>

          <Can
            permission={PERMISSIONS.INCIDENT_CREATE}
            fallback={
              <Button
                disabled
                title="Недостаточно прав для регистрации инцидента"
              >
                Зарегистрировать инцидент
              </Button>
            }
          >
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
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, title: e.target.value }))
                      }
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
                        onChange={(e) =>
                          setForm((prev) => ({
                            ...prev,
                            incident_type: e.target.value,
                          }))
                        }
                      >
                        {INCIDENT_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="inc-severity">Тяжесть</Label>
                      <select
                        id="inc-severity"
                        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                        value={form.severity}
                        onChange={(e) =>
                          setForm((prev) => ({
                            ...prev,
                            severity: e.target.value,
                          }))
                        }
                      >
                        {SEVERITY_LEVELS.map((s) => (
                          <option key={s} value={s}>
                            {SEVERITY_LABELS[s] ?? s}
                          </option>
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
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          occurred_at: e.target.value,
                        }))
                      }
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="inc-company">Компания *</Label>
                      <select
                        id="inc-company"
                        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                        value={form.company_id}
                        onChange={(e) =>
                          setForm((prev) => ({
                            ...prev,
                            company_id: e.target.value,
                          }))
                        }
                      >
                        <option value="">Выберите компанию</option>
                        {companies.map((company) => (
                          <option key={company.id} value={company.id}>
                            {company.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    {/* Срез-44 (in01, разд. 54.2): дисциплина — на первом
                        уровне, а не под «Дополнительно». Разметка нужна В
                        МОМЕНТ регистрации: потом инцидент на ОПО никто не
                        отличит от микротравмы, и отчёт в Ростехнадзор не
                        сможет подсказать число. Пусто — «не размечено». */}
                    <div className="space-y-1.5">
                      <Label htmlFor="inc-discipline">Дисциплина</Label>
                      <select
                        id="inc-discipline"
                        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                        value={form.discipline}
                        onChange={(e) =>
                          setForm((prev) => ({
                            ...prev,
                            discipline: e.target.value,
                          }))
                        }
                      >
                        <option value="">— Не размечена —</option>
                        {Object.entries(TRAINING_DISCIPLINE_TITLES).map(
                          ([code, title]) => (
                            <option key={code} value={code}>
                              {title}
                            </option>
                          ),
                        )}
                      </select>
                    </div>
                  </div>
                  {/* BIZ-59 (разд. 59.3, три уровня раскрытия): необязательные
                      поля уходят на второй уровень. При регистрации инцидента
                      важна скорость — площадку и подробности дописывают потом,
                      а требовать их сразу значит задержать саму регистрацию. */}
                  <details className="space-y-1.5">
                    <summary className="cursor-pointer text-sm text-muted-foreground">
                      Дополнительно
                    </summary>
                    <div className="space-y-4 pt-3">
                      <div className="space-y-1.5">
                        <Label htmlFor="inc-site">ID площадки</Label>
                        <Input
                          id="inc-site"
                          value={form.site_id}
                          onChange={(e) =>
                            setForm((prev) => ({
                              ...prev,
                              site_id: e.target.value,
                            }))
                          }
                          placeholder="UUID площадки (опционально)"
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor="inc-desc">Описание</Label>
                        <Textarea
                          id="inc-desc"
                          value={form.description}
                          onChange={(e) =>
                            setForm((prev) => ({
                              ...prev,
                              description: e.target.value,
                            }))
                          }
                          placeholder="Подробное описание произошедшего"
                          rows={3}
                        />
                      </div>
                    </div>
                  </details>
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="outline"
                      onClick={() => setCreateOpen(false)}
                    >
                      Отмена
                    </Button>
                    <Button
                      disabled={creating}
                      onClick={() => void handleCreate()}
                    >
                      {creating ? "Сохранение…" : "Зарегистрировать"}
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </Can>
        </div>
      </div>

      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      {focusedEntityId && focusedEntityType === "incident" ? (
        <Card>
          <CardContent className="py-4" data-testid="incident-focus-card">
            <div className="text-sm font-semibold">
              Фокус инцидента из рабочего пространства
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {focusedIncident
                ? `${focusedIncident.title} · ${INCIDENT_STATUS_LABELS[focusedIncident.status] ?? focusedIncident.status}`
                : `Инцидент ${focusedEntityId.slice(0, 8)} загружается...`}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="ghost" asChild>
                <Link to="/incidents">Сбросить фокус</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
      {loading ? <LoadingScreen label="Загрузка инцидентов" /> : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Инциденты и расследования</CardTitle>
        </CardHeader>
        <CardContent>
          {!loading && items.length === 0 ? (
            <EmptyState
              title="Инциденты не найдены"
              description="Снимите фильтр или зарегистрируйте новый инцидент."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Событие</TableHead>
                  <TableHead>Тип</TableHead>
                  <TableHead>Тяжесть</TableHead>
                  <TableHead>Площадка</TableHead>
                  <TableHead>Дата</TableHead>
                  <TableHead>Статус</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((incident) => (
                  <TableRow key={incident.id}>
                    <TableCell className="font-medium">{incident.id}</TableCell>
                    <TableCell>
                      <div>{incident.title}</div>
                      {/* дисциплина — подписью под событием, а не восьмой
                          колонкой: бюджет таблицы — семь (разд. 59.2) */}
                      {incident.discipline_label ? (
                        <div className="text-xs text-muted-foreground">
                          {incident.discipline_label}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      {INCIDENT_TYPE_LABELS[incident.incident_type] ??
                        incident.incident_type}
                    </TableCell>
                    <TableCell>
                      {incident.severity
                        ? (SEVERITY_LABELS[incident.severity] ??
                          incident.severity)
                        : "—"}
                    </TableCell>
                    <TableCell>{incident.site_id}</TableCell>
                    <TableCell>{formatDate(incident.occurred_at)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={incident.status} />
                        <span className="text-xs text-muted-foreground">
                          {INCIDENT_STATUS_LABELS[incident.status] ??
                            incident.status}
                        </span>
                      </div>
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
