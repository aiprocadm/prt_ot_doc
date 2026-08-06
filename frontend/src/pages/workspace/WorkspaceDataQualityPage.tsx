import {
  AlertTriangle,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { dataQualityApi } from "@/api/dataQuality";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import type {
  DataQualityIssueDto,
  DataQualityIssueSeverity,
  DataQualityReportDto,
} from "@/types/dto/dataQuality";

const SEVERITY_LABELS: Record<DataQualityIssueSeverity | string, string> = {
  critical: "Критично",
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
};

const ISSUE_TYPE_LABELS: Record<string, string> = {
  missing_field: "Отсутствуют поля",
  broken_relationship: "Битая связь",
  expired_record: "Просрочено",
  duplicate: "Дубликат",
  invalid_value: "Некорректное значение",
  data_mismatch: "Несоответствие данных",
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  person: "Сотрудники",
  company: "Контрагенты",
  site: "Площадки",
  workplace: "Рабочие места",
  document: "Документы",
  medical_exam: "Медосмотры",
  training: "Обучение",
  permit: "Допуски",
  ppe_issue: "СИЗ (выдачи)",
  incident: "Инциденты",
  briefing: "Инструктажи",
};

const SEVERITY_BADGE: Record<
  string,
  { variant: "default" | "secondary" | "destructive"; className?: string }
> = {
  critical: { variant: "destructive" },
  high: {
    variant: "destructive",
    className: "bg-orange-600 hover:bg-orange-600/80 text-white",
  },
  medium: { variant: "secondary", className: "bg-amber-200 text-amber-900" },
  low: { variant: "secondary" },
};

const ENTITY_DRILL_DOWN: Record<string, (id: string) => string> = {
  person: (id) => `/persons?focus=${encodeURIComponent(id)}`,
  company: (id) => `/companies?focus=${encodeURIComponent(id)}`,
  site: (id) => `/companies?site=${encodeURIComponent(id)}`,
  workplace: (id) => `/risk?workplace=${encodeURIComponent(id)}`,
  document: (id) => `/documents?focus=${encodeURIComponent(id)}`,
  medical_exam: (id) => `/medical?focus=${encodeURIComponent(id)}`,
  training: (id) => `/training?focus=${encodeURIComponent(id)}`,
  permit: (id) => `/contractors?permit=${encodeURIComponent(id)}`,
  ppe_issue: (id) => `/ppe?focus=${encodeURIComponent(id)}`,
  incident: (id) => `/incidents?focus=${encodeURIComponent(id)}`,
};

const labelFor = (map: Record<string, string>, key: string) => map[key] ?? key;

const formatPercent = (value: number) => `${Math.round(value * 10) / 10}%`;

const formatDate = (iso: string | undefined | null) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso ?? "—";
  }
};

const drillDownHref = (issue: DataQualityIssueDto): string | null => {
  const builder = ENTITY_DRILL_DOWN[issue.affected_entity_type];
  if (!builder) return null;
  if (!issue.affected_entity_id) return null;
  return builder(issue.affected_entity_id);
};

type SeverityFilter = "all" | DataQualityIssueSeverity;

export default function WorkspaceDataQualityPage() {
  const [report, setReport] = useState<DataQualityReportDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [entityFilter, setEntityFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dataQualityApi.getReport();
      setReport(data);
    } catch (err) {
      setError(
        (err as ApiError) ?? {
          status: 0,
          message: "Не удалось загрузить отчёт",
          field_errors: [],
        },
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredIssues = useMemo(() => {
    if (!report) return [] as DataQualityIssueDto[];
    return report.issues.filter((issue) => {
      if (severityFilter !== "all" && issue.severity !== severityFilter)
        return false;
      if (entityFilter !== "all" && issue.affected_entity_type !== entityFilter)
        return false;
      if (typeFilter !== "all" && issue.issue_type !== typeFilter) return false;
      return true;
    });
  }, [report, severityFilter, entityFilter, typeFilter]);

  const severityCards = useMemo(() => {
    const completeness = report?.completeness_percent ?? 0;
    return [
      {
        key: "completeness" as const,
        label: "Полнота данных",
        value: report ? formatPercent(completeness) : "—",
        description: "Доля корректных записей по итогам всех правил",
        icon: completeness >= 90 ? ShieldCheck : ShieldAlert,
        tone:
          completeness >= 90
            ? "border-emerald-500/40 bg-emerald-50 text-emerald-900"
            : completeness >= 70
              ? "border-amber-500/40 bg-amber-50 text-amber-900"
              : "border-destructive/40 bg-destructive/10 text-destructive",
      },
      {
        key: "critical" as const,
        label: "Критичные",
        value: report ? String(report.critical_issues) : "—",
        description: "Блокеры релиза и инспекций",
        icon: AlertTriangle,
        tone: "border-destructive/40 bg-destructive/10 text-destructive",
      },
      {
        key: "high" as const,
        label: "Высокий риск",
        value: report ? String(report.high_issues) : "—",
        description: "Требуют внимания в ближайшие сутки",
        icon: AlertTriangle,
        tone: "border-orange-500/40 bg-orange-50 text-orange-900",
      },
      {
        key: "medium" as const,
        label: "Средний риск",
        value: report ? String(report.medium_issues) : "—",
        description: "К плану следующей итерации качества",
        icon: AlertTriangle,
        tone: "border-amber-500/40 bg-amber-50 text-amber-900",
      },
      {
        key: "low" as const,
        label: "Низкий риск",
        value: report ? String(report.low_issues) : "—",
        description: "Информационные предупреждения",
        icon: AlertTriangle,
        tone: "border-muted bg-muted/30 text-muted-foreground",
      },
    ];
  }, [report]);

  const entityOptions = useMemo(() => {
    if (!report)
      return [] as Array<{ value: string; label: string; count: number }>;
    return Object.entries(report.entity_breakdown)
      .map(([value, count]) => ({
        value,
        label: labelFor(ENTITY_TYPE_LABELS, value),
        count,
      }))
      .sort((a, b) => b.count - a.count);
  }, [report]);

  const typeOptions = useMemo(() => {
    if (!report)
      return [] as Array<{ value: string; label: string; count: number }>;
    return Object.entries(report.issue_breakdown)
      .map(([value, count]) => ({
        value,
        label: labelFor(ISSUE_TYPE_LABELS, value),
        count,
      }))
      .sort((a, b) => b.count - a.count);
  }, [report]);

  const totalChecked = useMemo(() => {
    if (!report) return 0;
    return report.check_results.reduce(
      (acc, item) => acc + (item.total_checked ?? 0),
      0,
    );
  }, [report]);

  return (
    <div className="space-y-6 p-6">
      <Breadcrumb
        items={[
          { label: "Главная", to: "/dashboard" },
          { label: "Качество данных" },
        ]}
      />

      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Качество данных
          </h1>
          <p className="text-muted-foreground mt-1 max-w-2xl text-sm">
            Сводный отчёт по полноте и связности справочников: критичные пробелы
            по сотрудникам, контрагентам, документам, допускам и СИЗ. Источник —{" "}
            <code>/data-quality/report</code>.
          </p>
          {report ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Обновлено: {formatDate(report.generated_at)} · проверок:{" "}
              {report.check_results.length} · записей: {totalChecked}
            </p>
          ) : null}
        </div>
        <Button
          type="button"
          variant="secondary"
          onClick={load}
          disabled={loading}
          className="self-start md:self-auto"
        >
          <RefreshCw
            className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          Обновить
        </Button>
      </div>

      <ErrorState error={error ?? undefined} onRetry={load} />

      {loading && !report ? (
        <LoadingScreen label="Расчёт качества данных" />
      ) : null}

      {!loading && !error && report ? (
        <>
          <section
            aria-label="Сводка качества"
            className="grid gap-4 md:grid-cols-2 xl:grid-cols-5"
          >
            {severityCards.map((card) => (
              <Card
                key={card.key}
                className={`border ${card.tone}`}
                role="status"
                aria-label={`${card.label}: ${card.value}`}
              >
                <CardHeader className="space-y-1 pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-medium">
                      {card.label}
                    </CardTitle>
                    <card.icon
                      className="h-4 w-4 opacity-80"
                      aria-hidden="true"
                    />
                  </div>
                </CardHeader>
                <CardContent className="space-y-1">
                  <div className="text-3xl font-semibold">{card.value}</div>
                  <p className="text-xs opacity-80">{card.description}</p>
                </CardContent>
              </Card>
            ))}
          </section>

          <section
            aria-label="Срезы качества"
            className="grid gap-4 md:grid-cols-2"
          >
            <Card>
              <CardHeader>
                <CardTitle className="text-base">По типу проблемы</CardTitle>
                <CardDescription>
                  Разбивка нарушений по rule-классам бэкенда.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {typeOptions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Нарушений нет — все правила прошли.
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {typeOptions.map((option) => (
                      <li
                        key={option.value}
                        className="flex items-center justify-between text-sm"
                      >
                        <button
                          type="button"
                          className={`text-left hover:underline ${typeFilter === option.value ? "font-semibold text-primary" : ""}`}
                          onClick={() =>
                            setTypeFilter(
                              typeFilter === option.value
                                ? "all"
                                : option.value,
                            )
                          }
                          aria-pressed={typeFilter === option.value}
                        >
                          {option.label}
                        </button>
                        <Badge variant="secondary">{option.count}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">По сущностям</CardTitle>
                <CardDescription>
                  Куда падает больше всего проблем — для drill-down в реестры.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {entityOptions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Сущностей с нарушениями не найдено.
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {entityOptions.map((option) => (
                      <li
                        key={option.value}
                        className="flex items-center justify-between text-sm"
                      >
                        <button
                          type="button"
                          className={`text-left hover:underline ${entityFilter === option.value ? "font-semibold text-primary" : ""}`}
                          onClick={() =>
                            setEntityFilter(
                              entityFilter === option.value
                                ? "all"
                                : option.value,
                            )
                          }
                          aria-pressed={entityFilter === option.value}
                        >
                          {option.label}
                        </button>
                        <Badge variant="secondary">{option.count}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </section>

          <section aria-label="Топ нарушений" className="space-y-3">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-lg font-semibold">Топ нарушений</h2>
                <p className="text-xs text-muted-foreground">
                  Показано до 20 наиболее приоритетных проблем; используйте
                  фильтры по карточкам выше.
                </p>
              </div>
              <div
                className="flex flex-wrap items-center gap-2"
                role="toolbar"
                aria-label="Фильтр по уровню риска"
              >
                {(
                  [
                    "all",
                    "critical",
                    "high",
                    "medium",
                    "low",
                  ] as SeverityFilter[]
                ).map((value) => (
                  <Button
                    key={value}
                    type="button"
                    size="sm"
                    variant={severityFilter === value ? "default" : "outline"}
                    onClick={() => setSeverityFilter(value)}
                    aria-pressed={severityFilter === value}
                  >
                    {value === "all" ? "Все" : labelFor(SEVERITY_LABELS, value)}
                  </Button>
                ))}
                {typeFilter !== "all" || entityFilter !== "all" ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setTypeFilter("all");
                      setEntityFilter("all");
                    }}
                  >
                    Сбросить фильтры
                  </Button>
                ) : null}
              </div>
            </div>

            {filteredIssues.length === 0 ? (
              <EmptyState
                title={
                  report.total_issues === 0
                    ? "Все проверки пройдены"
                    : "Нет проблем под текущие фильтры"
                }
                description={
                  report.total_issues === 0
                    ? "Сводный отчёт не зафиксировал нарушений на момент последнего расчёта."
                    : "Снимите фильтры или выберите другую категорию выше."
                }
              />
            ) : (
              <Card>
                <CardContent className="px-0 pb-2 pt-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[110px]">Уровень</TableHead>
                        <TableHead className="w-[180px]">Тип</TableHead>
                        <TableHead>Описание</TableHead>
                        <TableHead className="w-[160px]">Сущность</TableHead>
                        <TableHead className="w-[140px] text-right">
                          Действие
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredIssues.map((issue) => {
                        const severity = String(issue.severity);
                        const badge = SEVERITY_BADGE[severity] ?? {
                          variant: "secondary",
                        };
                        const drillHref = drillDownHref(issue);
                        return (
                          <TableRow key={issue.id}>
                            <TableCell>
                              <Badge
                                variant={badge.variant}
                                className={badge.className}
                              >
                                {labelFor(SEVERITY_LABELS, severity)}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-sm">
                              {labelFor(
                                ISSUE_TYPE_LABELS,
                                String(issue.issue_type),
                              )}
                            </TableCell>
                            <TableCell className="text-sm">
                              <div className="font-medium">{issue.title}</div>
                              {issue.description ? (
                                <div className="text-muted-foreground text-xs">
                                  {issue.description}
                                </div>
                              ) : null}
                              {issue.affected_entity_name ? (
                                <div className="text-xs text-muted-foreground">
                                  Объект: {issue.affected_entity_name}
                                </div>
                              ) : null}
                            </TableCell>
                            <TableCell className="text-sm">
                              {labelFor(
                                ENTITY_TYPE_LABELS,
                                issue.affected_entity_type,
                              )}
                            </TableCell>
                            <TableCell className="text-right">
                              {drillHref ? (
                                <Link
                                  to={drillHref}
                                  className="text-sm font-medium text-primary hover:underline"
                                >
                                  Открыть →
                                </Link>
                              ) : (
                                <span className="text-xs text-muted-foreground">
                                  —
                                </span>
                              )}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}
          </section>

          <section aria-label="Покрытие правилами" className="space-y-3">
            <div>
              <h2 className="text-lg font-semibold">Покрытие правилами</h2>
              <p className="text-xs text-muted-foreground">
                Какие проверки запускались, сколько записей просмотрено и
                сколько проблем найдено.
              </p>
            </div>
            <Card>
              <CardContent className="px-0 pb-2 pt-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Правило</TableHead>
                      <TableHead>Описание</TableHead>
                      <TableHead className="w-[120px] text-right">
                        Проверено
                      </TableHead>
                      <TableHead className="w-[120px] text-right">
                        Найдено
                      </TableHead>
                      <TableHead className="w-[120px] text-right">
                        Время, мс
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {report.check_results.map((result) => (
                      <TableRow key={result.rule_name}>
                        <TableCell className="font-mono text-xs">
                          {result.rule_name}
                        </TableCell>
                        <TableCell className="text-sm">
                          {result.rule_description}
                        </TableCell>
                        <TableCell className="text-right text-sm">
                          {result.total_checked}
                        </TableCell>
                        <TableCell className="text-right text-sm">
                          <Badge
                            variant={
                              result.issues_found > 0
                                ? "destructive"
                                : "secondary"
                            }
                          >
                            {result.issues_found}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right text-sm text-muted-foreground">
                          {Math.round(result.execution_time_ms)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </section>
        </>
      ) : null}
    </div>
  );
}
