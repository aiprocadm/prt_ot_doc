import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { analyticsApi } from "@/api/analyticsApi";
import { TrendLineChart } from "@/components/analytics/TrendLineChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import type {
  AnalyticsFiltersDto,
  BreakdownDto,
  DashboardWidgetsDto,
  DirectoryItemDto,
  ExecutiveDashboardDto,
  TrendSeriesDto,
} from "@/types/dto/analytics";

const TREND_METRICS = [
  { key: "incidents", title: "Инциденты" },
  { key: "compliance", title: "Просрочки соответствия" },
  { key: "packages", title: "Пакеты документов" },
  { key: "trainings", title: "Просроченное обучение" },
  { key: "inspections", title: "Проверки" },
  { key: "ppe", title: "СИЗ" },
] as const;

const KPI_LABELS: Record<string, string> = {
  packages_total: "Пакеты документов",
  overdue_compliance_items: "Блокирующие несоответствия",
  open_incidents: "Открытые инциденты",
  open_inspections: "Открытые проверки",
  trainings_overdue: "Просроченное обучение",
  ppe_overdue: "Просроченные СИЗ",
  prescriptions_overdue: "Просроченные предписания",
  plan_tasks_overdue: "Просроченные задачи планов",
  workflow_open: "Открытые workflow-задачи",
  workflow_sla_breached: "Нарушен SLA",
};

const BREAKDOWN_METRIC_LABELS: Record<string, string> = {
  incidents_open: "Инциденты",
  prescriptions_overdue: "Предписания",
  trainings_overdue: "Обучение",
  ppe_overdue: "СИЗ",
  risks_high: "Высокие риски",
  workers_blocked: "Блокированные работники",
  missing_docs: "Нет документов",
  missing_training: "Нет обучения",
  overdue_items: "Просрочки",
  active_packages: "Активные пакеты",
};

const DIMENSIONS = [
  { key: "company", label: "По компаниям" },
  { key: "site", label: "По объектам" },
  { key: "contractor", label: "По подрядчикам" },
  // Доп. №1 разд. 57.4: «директорский» взгляд — вся безопасность предприятия
  // по дисциплинам на одном экране, а не восемь экранов контуров.
  { key: "discipline", label: "По дисциплинам" },
] as const;

const PERIODS = [
  { key: "daily", label: "День" },
  { key: "weekly", label: "Неделя" },
  { key: "monthly", label: "Месяц" },
] as const;

const SUB_DASHBOARDS = [
  { to: "/dashboard/executive", label: "Executive" },
  { to: "/dashboard/safety", label: "Безопасность" },
  { to: "/dashboard/training", label: "Обучение" },
  { to: "/dashboard/ppe", label: "СИЗ" },
  { to: "/dashboard/client-delivery", label: "Клиентская доставка" },
] as const;

type Period = (typeof PERIODS)[number]["key"];
type Dimension = (typeof DIMENSIONS)[number]["key"];

export default function ManagementDashboardPage() {
  const [filters, setFilters] = useState<AnalyticsFiltersDto>({});
  const [period, setPeriod] = useState<Period>("daily");
  const [dimension, setDimension] = useState<Dimension>("site");

  const companiesRes = useAsyncResource<{ items?: DirectoryItemDto[] }>({
    loader: useCallback(() => analyticsApi.getCompanies(), []),
    initialData: { items: [] },
    errorMessage: "Не удалось загрузить компании",
  });
  const sitesRes = useAsyncResource<{ items?: DirectoryItemDto[] }>({
    loader: useCallback(() => analyticsApi.getSites(), []),
    initialData: { items: [] },
    errorMessage: "Не удалось загрузить объекты",
  });
  // /contractors/registry живёт в домене подрядчиков и закрыт своими ролями —
  // для management-ролей (line_manager/hr/ot_specialist) это ожидаемый 403.
  // Деградация тихая: селект просто не рендерится (см. ниже), страницу не рушим.
  const contractorsRes = useAsyncResource<{ items?: DirectoryItemDto[] }>({
    loader: useCallback(() => analyticsApi.getContractors(), []),
    initialData: { items: [] },
    errorMessage: "Не удалось загрузить подрядчиков",
  });

  const executiveRes = useAsyncResource<ExecutiveDashboardDto | null>({
    loader: useCallback(() => analyticsApi.getExecutive(filters), [filters]),
    initialData: null,
    errorMessage: "Не удалось загрузить сводные показатели",
  });
  const overdueRes = useAsyncResource<DashboardWidgetsDto | null>({
    loader: useCallback(
      () => analyticsApi.getDashboard("overdue", filters),
      [filters],
    ),
    initialData: null,
    errorMessage: "Не удалось загрузить просрочки",
  });
  const slaRes = useAsyncResource<DashboardWidgetsDto | null>({
    loader: useCallback(
      () => analyticsApi.getDashboard("sla-load", filters),
      [filters],
    ),
    initialData: null,
    errorMessage: "Не удалось загрузить SLA-нагрузку",
  });
  const trendsRes = useAsyncResource<TrendSeriesDto[]>({
    loader: useCallback(
      () =>
        Promise.all(
          TREND_METRICS.map((m) => analyticsApi.getTrend(m.key, period)),
        ),
      [period],
    ),
    initialData: [],
    errorMessage: "Не удалось загрузить тренды",
  });
  const breakdownRes = useAsyncResource<BreakdownDto | null>({
    loader: useCallback(
      () =>
        analyticsApi.getBreakdown(dimension, {
          date_from: filters.date_from,
          date_to: filters.date_to,
        }),
      [dimension, filters.date_from, filters.date_to],
    ),
    initialData: null,
    errorMessage: "Не удалось загрузить разрез",
  });

  const kpiCards = useMemo(() => {
    const widgets: Record<string, number> = {
      ...(executiveRes.data?.dashboard?.widgets ?? {}),
      ...(overdueRes.data?.widgets ?? {}),
      ...(slaRes.data?.widgets ?? {}),
    };
    return Object.entries(KPI_LABELS)
      .filter(([key]) => key in widgets)
      .map(([key, label]) => ({ key, label, value: widgets[key] }));
  }, [executiveRes.data, overdueRes.data, slaRes.data]);

  const breakdown = breakdownRes.data;
  const metricKeys = useMemo(() => {
    if (!breakdown || breakdown.items.length === 0) return [];
    return Object.keys(breakdown.items[0]).filter(
      (k) => !["id", "name", "total_issues"].includes(k),
    );
  }, [breakdown]);
  const maxIssues = useMemo(
    () => Math.max(1, ...(breakdown?.items.map((i) => i.total_issues) ?? [1])),
    [breakdown],
  );

  const setFilter = useCallback(
    (key: keyof AnalyticsFiltersDto, value: string) => {
      setFilters((prev) => {
        const next = { ...prev };
        if (value) next[key] = value;
        else delete next[key];
        return next;
      });
    },
    [],
  );

  const applyRowFilter = useCallback(
    (rowId: string) => {
      if (dimension === "company") setFilter("company_id", rowId);
      else if (dimension === "site") setFilter("site_id", rowId);
      else if (dimension === "contractor") setFilter("contractor_id", rowId);
      // у дисциплины фильтра страницы нет: её число происшествий само ведёт в
      // реестр (ссылка в ячейке), а KPI по дисциплине не режутся
    },
    [dimension, setFilter],
  );

  if (companiesRes.loading || executiveRes.loading) return <LoadingScreen />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Управленческая аналитика</CardTitle>
          <CardDescription>
            KPI, тренды и разрез по компаниям / объектам / подрядчикам (vNext
            §24.2).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label htmlFor="ma-company">Компания</Label>
              <select
                id="ma-company"
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={filters.company_id ?? ""}
                onChange={(e) => setFilter("company_id", e.target.value)}
              >
                <option value="">— все —</option>
                {(companiesRes.data?.items ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="ma-site">Объект</Label>
              <select
                id="ma-site"
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={filters.site_id ?? ""}
                onChange={(e) => setFilter("site_id", e.target.value)}
              >
                <option value="">— все —</option>
                {(sitesRes.data?.items ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            {contractorsRes.error ? null : (
              <div className="space-y-1">
                <Label htmlFor="ma-contractor">Подрядчик</Label>
                <select
                  id="ma-contractor"
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                  value={filters.contractor_id ?? ""}
                  onChange={(e) => setFilter("contractor_id", e.target.value)}
                >
                  <option value="">— все —</option>
                  {(contractorsRes.data?.items ?? []).map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="space-y-1">
              <Label htmlFor="ma-from">С</Label>
              <Input
                id="ma-from"
                type="date"
                value={filters.date_from ?? ""}
                onChange={(e) => setFilter("date_from", e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="ma-to">По</Label>
              <Input
                id="ma-to"
                type="date"
                value={filters.date_to ?? ""}
                onChange={(e) => setFilter("date_to", e.target.value)}
              />
            </div>
            <Button variant="outline" onClick={() => setFilters({})}>
              Сбросить
            </Button>
          </div>
        </CardContent>
      </Card>

      {executiveRes.error ? (
        <ErrorState error={executiveRes.error} onRetry={executiveRes.reload} />
      ) : (
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
          {kpiCards.map((card) => (
            <Card key={card.key}>
              <CardHeader className="pb-2">
                <CardDescription>{card.label}</CardDescription>
                <CardTitle className="text-2xl">{card.value}</CardTitle>
              </CardHeader>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Тренды</CardTitle>
            <div className="flex gap-1">
              {PERIODS.map((p) => (
                <Button
                  key={p.key}
                  size="sm"
                  variant={period === p.key ? "default" : "outline"}
                  aria-pressed={period === p.key}
                  onClick={() => setPeriod(p.key)}
                >
                  {p.label}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {trendsRes.error ? (
            <ErrorState error={trendsRes.error} onRetry={trendsRes.reload} />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {TREND_METRICS.map((m, idx) => (
                <TrendLineChart
                  key={m.key}
                  title={m.title}
                  series={trendsRes.data?.[idx]?.series ?? []}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Разрез</CardTitle>
            <div className="flex gap-1">
              {DIMENSIONS.map((d) => (
                <Button
                  key={d.key}
                  size="sm"
                  variant={dimension === d.key ? "default" : "outline"}
                  aria-pressed={dimension === d.key}
                  onClick={() => setDimension(d.key)}
                >
                  {d.label}
                </Button>
              ))}
            </div>
          </div>
          <CardDescription>
            {dimension === "discipline"
              ? "Происшествия — по разметке дисциплины; «—» значит, что просрочки по этой дисциплине не считаются (не ноль)."
              : "Клик по строке применяет её как фильтр страницы."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {breakdownRes.error ? (
            <ErrorState
              error={breakdownRes.error}
              onRetry={breakdownRes.reload}
            />
          ) : !breakdown || breakdown.items.length === 0 ? (
            <EmptyState
              title="Нет данных"
              description="В этом разрезе пока пусто."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4">Название</th>
                    {metricKeys.map((k) => (
                      <th key={k} className="py-2 pr-4">
                        {BREAKDOWN_METRIC_LABELS[k] ?? k}
                      </th>
                    ))}
                    <th className="py-2">Всего проблем</th>
                  </tr>
                </thead>
                <tbody>
                  {breakdown.items.map((row) => {
                    // Строка "— без объекта —" (id=="") агрегирует записи без привязки
                    // к объекту — бэкенд не поддерживает семантику "site_id IS NULL"
                    // как фильтр, поэтому строка не кликабельна.
                    const clickable =
                      Boolean(row.id) && dimension !== "discipline";
                    return (
                      <tr
                        key={row.id || row.name}
                        className={`border-b last:border-0 hover:bg-muted/50 ${clickable ? "cursor-pointer" : ""}`}
                        onClick={() => {
                          if (!row.id) return;
                          applyRowFilter(row.id);
                        }}
                      >
                        <td className="py-2 pr-4">{row.name}</td>
                        {metricKeys.map((k) => (
                          <td key={k} className="py-2 pr-4">
                            {row[k] === null ? (
                              <span
                                className="text-muted-foreground"
                                title="По этой дисциплине не считается"
                              >
                                —
                              </span>
                            ) : dimension === "discipline" &&
                              k === "incidents_open" &&
                              row.id &&
                              Number(row[k]) > 0 ? (
                              <Link
                                to={`/incidents?discipline=${encodeURIComponent(row.id)}`}
                                className="text-primary underline"
                              >
                                {row[k]}
                              </Link>
                            ) : (
                              row[k]
                            )}
                          </td>
                        ))}
                        <td className="py-2">
                          <div className="flex items-center gap-2">
                            <span className="w-8 text-right">
                              {row.total_issues}
                            </span>
                            <div className="h-2 flex-1 rounded bg-muted">
                              <div
                                className="h-2 rounded bg-primary"
                                style={{
                                  width: `${(row.total_issues / maxIssues) * 100}%`,
                                }}
                              />
                            </div>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Профильные дашборды</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {SUB_DASHBOARDS.map((d) => (
              <Button key={d.to} asChild variant="outline">
                <Link to={d.to}>{d.label}</Link>
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
