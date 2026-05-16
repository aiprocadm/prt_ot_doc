import { Download, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { calendarApi } from "@/api/calendar";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import {
  CALENDAR_SLA_BANDS,
  CALENDAR_SOURCE_TYPES,
  type CalendarEventItemDto,
  type CalendarEventsResponseDto,
  type CalendarSlaBand,
  type CalendarSourceCountDto,
  type CalendarSourceType
} from "@/types/dto/calendar";
import { downloadBlob } from "@/utils/download";

type CalendarView = "day" | "week" | "month" | "year" | "list";

const VIEWS: { value: CalendarView; label: string }[] = [
  { value: "day", label: "День" },
  { value: "week", label: "Неделя" },
  { value: "month", label: "Месяц" },
  { value: "year", label: "Год" },
  { value: "list", label: "Список" }
];

const SOURCE_LABELS: Record<CalendarSourceType, string> = {
  medical_exam: "Медосмотры",
  ppe_issue: "СИЗ",
  permit: "Допуски",
  training_session: "Обучение",
  inspection: "Проверки",
  compliance_deadline: "Контрольные сроки",
  briefing_entry: "Инструктажи",
  calendar_event: "Прочие события"
};

const DRILL_DOWN: Partial<Record<CalendarSourceType, string>> = {
  medical_exam: "/medical",
  ppe_issue: "/ppe",
  permit: "/persons",
  training_session: "/training",
  inspection: "/inspections",
  compliance_deadline: "/workspace/data-quality",
  briefing_entry: "/briefings"
};

const SLA_BAND_LABELS: Record<CalendarSlaBand, string> = {
  overdue: "Просрочено",
  critical: "Критично",
  warning: "Внимание",
  ok: "В норме"
};

const isCalendarSource = (value: string): value is CalendarSourceType =>
  (CALENDAR_SOURCE_TYPES as readonly string[]).includes(value);

const isSlaBand = (value: string): value is CalendarSlaBand =>
  (CALENDAR_SLA_BANDS as readonly string[]).includes(value);

const isView = (value: string | null): value is CalendarView =>
  value === "day" || value === "week" || value === "month" || value === "year" || value === "list";

const parseSources = (raw: string | null): CalendarSourceType[] => {
  if (!raw) return [];
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0 && isCalendarSource(part)) as CalendarSourceType[];
};

const parseSlaBands = (raw: string | null): CalendarSlaBand[] => {
  if (!raw) return [];
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0 && isSlaBand(part)) as CalendarSlaBand[];
};

const startOfDay = (value: Date) => {
  const next = new Date(value);
  next.setHours(0, 0, 0, 0);
  return next;
};

const startOfWeek = (value: Date) => {
  const next = startOfDay(value);
  const day = next.getDay();
  const diff = (day + 6) % 7;
  next.setDate(next.getDate() - diff);
  return next;
};

const startOfMonth = (value: Date) => {
  const next = startOfDay(value);
  next.setDate(1);
  return next;
};

const startOfYear = (value: Date) => {
  const next = startOfDay(value);
  next.setMonth(0, 1);
  return next;
};

const formatBucketLabel = (view: CalendarView, key: string): string => {
  if (view === "day") return new Date(key).toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" });
  if (view === "week") {
    const start = new Date(key);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    return `Неделя ${start.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" })} — ${end.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" })}`;
  }
  if (view === "month") return new Date(key).toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
  if (view === "year") return new Date(key).toLocaleDateString("ru-RU", { year: "numeric" });
  return "Все события";
};

const bucketKeyFor = (view: CalendarView, isoDate: string): string => {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return isoDate;
  if (view === "day") return startOfDay(date).toISOString();
  if (view === "week") return startOfWeek(date).toISOString();
  if (view === "month") return startOfMonth(date).toISOString();
  if (view === "year") return startOfYear(date).toISOString();
  return "list";
};

const formatDateTime = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
};

const formatDateOnly = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  });
};

const buildDrillDown = (item: CalendarEventItemDto): string | null => {
  const base = DRILL_DOWN[item.source_type];
  if (!base) return null;
  return `${base}?focus=${encodeURIComponent(item.source_id)}`;
};

const SourceChip = ({
  source,
  selected,
  onToggle,
  count
}: {
  source: CalendarSourceCountDto;
  selected: boolean;
  onToggle: () => void;
  count: number;
}) => (
  <Button
    type="button"
    size="sm"
    variant={selected ? "default" : "outline"}
    onClick={onToggle}
    className="gap-2"
  >
    <span>{SOURCE_LABELS[source.source_type] ?? source.source_type}</span>
    <Badge variant={selected ? "secondary" : "outline"} className="px-1.5 text-[11px]">
      {count}
    </Badge>
    {source.overdue_count > 0 ? (
      <Badge variant="destructive" className="px-1.5 text-[11px]">
        {source.overdue_count}
      </Badge>
    ) : null}
  </Button>
);

const VarianceBadge = ({ days }: { days: number }) => {
  if (days === 0) {
    return <Badge variant="secondary">В срок</Badge>;
  }
  if (days > 0) {
    return <Badge variant="destructive">+{days} дн.</Badge>;
  }
  return (
    <Badge variant="outline" className="text-emerald-600 border-emerald-300">
      {days} дн.
    </Badge>
  );
};

const SLA_BAND_BADGE_CLASS: Record<CalendarSlaBand, string> = {
  overdue: "border-transparent bg-destructive text-destructive-foreground",
  critical: "border-transparent bg-orange-500 text-white",
  warning: "border-transparent bg-amber-400 text-amber-950",
  ok: "border-transparent bg-emerald-500 text-white"
};

const SlaBadge = ({ band }: { band: CalendarSlaBand }) => (
  <Badge variant="outline" className={SLA_BAND_BADGE_CLASS[band]} data-sla-band={band}>
    {SLA_BAND_LABELS[band]}
  </Badge>
);

const formatDaysToDueLabel = (days: number): string => {
  if (days === 0) return "Срок сегодня";
  if (days > 0) return `Осталось ${days} дн.`;
  return `Просрочено на ${Math.abs(days)} дн.`;
};

const DaysToDueChip = ({ days }: { days: number }) => (
  <Badge
    variant="outline"
    className="text-muted-foreground"
    data-testid="days-to-due-chip"
  >
    {formatDaysToDueLabel(days)}
  </Badge>
);

const EventRow = ({
  item,
  includeFact,
  includeSla
}: {
  item: CalendarEventItemDto;
  includeFact: boolean;
  includeSla: boolean;
}) => {
  const link = buildDrillDown(item);
  return (
    <TableRow>
      <TableCell className="text-sm">{formatDateTime(item.starts_at)}</TableCell>
      <TableCell className="text-sm font-medium">
        {link ? (
          <Link to={link} className="text-primary underline-offset-4 hover:underline">
            {item.title}
          </Link>
        ) : (
          item.title
        )}
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">
        {SOURCE_LABELS[item.source_type] ?? item.source_type}
      </TableCell>
      <TableCell className="text-sm">{item.status ?? "—"}</TableCell>
      {includeFact ? (
        <>
          <TableCell className="text-sm">{formatDateOnly(item.expected_at)}</TableCell>
          <TableCell className="text-sm">{formatDateOnly(item.actual_at)}</TableCell>
          <TableCell>
            {typeof item.variance_days === "number" ? (
              <VarianceBadge days={item.variance_days} />
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </TableCell>
        </>
      ) : null}
      {includeSla ? (
        <TableCell>
          <div className="flex flex-wrap items-center gap-2">
            {item.sla_band ? <SlaBadge band={item.sla_band} /> : (
              <span className="text-muted-foreground">—</span>
            )}
            {typeof item.days_to_due === "number" ? (
              <DaysToDueChip days={item.days_to_due} />
            ) : null}
          </div>
        </TableCell>
      ) : null}
      <TableCell>
        {item.is_overdue ? (
          <Badge variant="destructive">Просрочен</Badge>
        ) : (
          <Badge variant="outline">В срок</Badge>
        )}
      </TableCell>
    </TableRow>
  );
};

const CalendarPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialView = isView(searchParams.get("view")) ? (searchParams.get("view") as CalendarView) : "month";
  const initialSources = parseSources(searchParams.get("sources"));
  const initialPersonId = searchParams.get("person_id") ?? "";
  const initialSiteId = searchParams.get("site_id") ?? "";
  const initialIncludeFact = searchParams.get("include_fact") === "1";
  const initialIncludeSla = searchParams.get("include_sla") === "1";
  const initialSlaBands = parseSlaBands(searchParams.get("sla_bands"));

  const [view, setView] = useState<CalendarView>(initialView);
  const [selectedSources, setSelectedSources] = useState<CalendarSourceType[]>(initialSources);
  const [personId, setPersonId] = useState(initialPersonId);
  const [siteId, setSiteId] = useState(initialSiteId);
  const [appliedPersonId, setAppliedPersonId] = useState(initialPersonId);
  const [appliedSiteId, setAppliedSiteId] = useState(initialSiteId);
  const [includeFact, setIncludeFact] = useState(initialIncludeFact);
  const [includeSla, setIncludeSla] = useState(initialIncludeSla || initialSlaBands.length > 0);
  const [selectedBands, setSelectedBands] = useState<CalendarSlaBand[]>(initialSlaBands);

  const [response, setResponse] = useState<CalendarEventsResponseDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [icsLoading, setIcsLoading] = useState(false);
  const [icsError, setIcsError] = useState<string | null>(null);

  const updateQueryParams = useCallback(
    (patch: {
      view?: CalendarView;
      sources?: CalendarSourceType[];
      person_id?: string;
      site_id?: string;
      include_fact?: boolean;
      include_sla?: boolean;
      sla_bands?: CalendarSlaBand[];
    }) => {
      const next = new URLSearchParams(searchParams);
      if (patch.view !== undefined) {
        if (patch.view === "month") next.delete("view");
        else next.set("view", patch.view);
      }
      if (patch.sources !== undefined) {
        if (patch.sources.length === 0) next.delete("sources");
        else next.set("sources", patch.sources.join(","));
      }
      if (patch.person_id !== undefined) {
        if (patch.person_id) next.set("person_id", patch.person_id);
        else next.delete("person_id");
      }
      if (patch.site_id !== undefined) {
        if (patch.site_id) next.set("site_id", patch.site_id);
        else next.delete("site_id");
      }
      if (patch.include_fact !== undefined) {
        if (patch.include_fact) next.set("include_fact", "1");
        else next.delete("include_fact");
      }
      if (patch.include_sla !== undefined) {
        if (patch.include_sla) next.set("include_sla", "1");
        else next.delete("include_sla");
      }
      if (patch.sla_bands !== undefined) {
        if (patch.sla_bands.length === 0) next.delete("sla_bands");
        else next.set("sla_bands", patch.sla_bands.join(","));
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await calendarApi.getEvents({
        source_types: selectedSources.length > 0 ? selectedSources : undefined,
        person_id: appliedPersonId || undefined,
        site_id: appliedSiteId || undefined,
        include_fact: includeFact || undefined,
        include_sla: includeSla || undefined
      });
      setResponse(data);
    } catch (nextError) {
      setError(
        (nextError as ApiError) ?? {
          status: 0,
          message: "Не удалось загрузить календарь",
          field_errors: []
        }
      );
    } finally {
      setLoading(false);
    }
  }, [selectedSources, appliedPersonId, appliedSiteId, includeFact, includeSla]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleSource = useCallback(
    (source: CalendarSourceType) => {
      setSelectedSources((current) => {
        const next = current.includes(source)
          ? current.filter((value) => value !== source)
          : [...current, source];
        updateQueryParams({ sources: next });
        return next;
      });
    },
    [updateQueryParams]
  );

  const changeView = useCallback(
    (next: CalendarView) => {
      setView(next);
      updateQueryParams({ view: next });
    },
    [updateQueryParams]
  );

  const applyFilters = useCallback(() => {
    setAppliedPersonId(personId.trim());
    setAppliedSiteId(siteId.trim());
    updateQueryParams({
      person_id: personId.trim(),
      site_id: siteId.trim()
    });
  }, [personId, siteId, updateQueryParams]);

  const resetFilters = useCallback(() => {
    setSelectedSources([]);
    setPersonId("");
    setSiteId("");
    setAppliedPersonId("");
    setAppliedSiteId("");
    setIncludeFact(false);
    setIncludeSla(false);
    setSelectedBands([]);
    updateQueryParams({
      sources: [],
      person_id: "",
      site_id: "",
      include_fact: false,
      include_sla: false,
      sla_bands: []
    });
  }, [updateQueryParams]);

  const togglePlanFact = useCallback(() => {
    setIncludeFact((current) => {
      const next = !current;
      updateQueryParams({ include_fact: next });
      return next;
    });
  }, [updateQueryParams]);

  const toggleSla = useCallback(() => {
    setIncludeSla((current) => {
      const next = !current;
      updateQueryParams({ include_sla: next });
      if (!next) {
        setSelectedBands([]);
        updateQueryParams({ sla_bands: [] });
      }
      return next;
    });
  }, [updateQueryParams]);

  const toggleBand = useCallback(
    (band: CalendarSlaBand) => {
      setSelectedBands((current) => {
        const next = current.includes(band)
          ? current.filter((value) => value !== band)
          : [...current, band];
        updateQueryParams({ sla_bands: next });
        return next;
      });
    },
    [updateQueryParams]
  );

  const handleDownloadIcs = useCallback(async () => {
    setIcsLoading(true);
    setIcsError(null);
    try {
      const blob = await calendarApi.downloadIcs({
        source_types: selectedSources.length > 0 ? selectedSources : undefined,
        person_id: appliedPersonId || undefined,
        site_id: appliedSiteId || undefined,
        include_fact: includeFact || undefined,
        include_sla: includeSla || undefined
      });
      const today = new Date().toISOString().slice(0, 10);
      downloadBlob(blob, `calendar-${today}.ics`);
    } catch (nextError) {
      const message =
        (nextError as ApiError | undefined)?.message ?? "Не удалось скачать .ics";
      setIcsError(message);
    } finally {
      setIcsLoading(false);
    }
  }, [selectedSources, appliedPersonId, appliedSiteId, includeFact, includeSla]);

  const items = useMemo(() => {
    const all = response?.items ?? [];
    if (!includeSla || selectedBands.length === 0) return all;
    return all.filter((item) => item.sla_band && selectedBands.includes(item.sla_band));
  }, [response, includeSla, selectedBands]);

  const buckets = useMemo(() => {
    if (items.length === 0) return [];
    const map = new Map<string, CalendarEventItemDto[]>();
    items.forEach((item) => {
      const key = bucketKeyFor(view, item.starts_at);
      const list = map.get(key) ?? [];
      list.push(item);
      map.set(key, list);
    });
    return [...map.entries()]
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([key, list]) => ({
        key,
        label: formatBucketLabel(view, key),
        items: list,
        overdue: list.filter((entry) => entry.is_overdue).length
      }));
  }, [items, view]);

  const factSummary = useMemo(() => {
    if (!includeFact || items.length === 0) {
      return { withFact: 0, late: 0, early: 0, onTime: 0 };
    }
    let withFact = 0;
    let late = 0;
    let early = 0;
    let onTime = 0;
    items.forEach((item) => {
      if (typeof item.variance_days !== "number") return;
      withFact += 1;
      if (item.variance_days > 0) late += 1;
      else if (item.variance_days < 0) early += 1;
      else onTime += 1;
    });
    return { withFact, late, early, onTime };
  }, [includeFact, items]);

  const slaSummary = useMemo(() => {
    const empty = { overdue: 0, critical: 0, warning: 0, ok: 0 };
    const all = response?.items ?? [];
    if (!includeSla || all.length === 0) return empty;
    return all.reduce((acc, item) => {
      if (item.sla_band && item.sla_band in acc) {
        acc[item.sla_band] += 1;
      }
      return acc;
    }, { ...empty });
  }, [includeSla, response]);

  const counts = response?.by_source ?? [];
  const total = response?.total ?? 0;
  const overdueTotal = response?.overdue_count ?? 0;
  const generatedAtLabel = response?.generated_at ? formatDateTime(response.generated_at) : null;
  const filtersActive =
    selectedSources.length > 0 ||
    appliedPersonId.length > 0 ||
    appliedSiteId.length > 0 ||
    includeFact ||
    includeSla ||
    selectedBands.length > 0;

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Умный календарь" }]} />
      <Card>
        <CardHeader className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <CardTitle>Умный календарь</CardTitle>
            <CardDescription>
              Сводный поток медосмотров, СИЗ, допусков, обучений, проверок, контрольных сроков и инструктажей с подсветкой просрочек и сравнением план/факт.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant={includeFact ? "default" : "outline"}
              size="sm"
              onClick={togglePlanFact}
              aria-pressed={includeFact}
            >
              {includeFact ? "Скрыть план/факт" : "Сравнить план/факт"}
            </Button>
            <Button
              type="button"
              variant={includeSla ? "default" : "outline"}
              size="sm"
              onClick={toggleSla}
              aria-pressed={includeSla}
            >
              {includeSla ? "Скрыть SLA" : "Показать SLA"}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleDownloadIcs()}
              disabled={icsLoading}
            >
              <Download className="mr-2 h-4 w-4" /> Скачать .ics
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw className="mr-2 h-4 w-4" /> Обновить
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase text-muted-foreground">Вид:</span>
            {VIEWS.map((option) => (
              <Button
                key={option.value}
                type="button"
                size="sm"
                variant={view === option.value ? "default" : "outline"}
                onClick={() => changeView(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {CALENDAR_SOURCE_TYPES.map((sourceType) => {
              const summary =
                counts.find((entry) => entry.source_type === sourceType) ?? {
                  source_type: sourceType,
                  count: 0,
                  overdue_count: 0
                };
              return (
                <SourceChip
                  key={sourceType}
                  source={summary}
                  count={summary.count}
                  selected={selectedSources.includes(sourceType)}
                  onToggle={() => toggleSource(sourceType)}
                />
              );
            })}
          </div>
          {includeSla ? (
            <div className="flex flex-wrap items-center gap-2" data-testid="sla-band-filter">
              <span className="text-xs uppercase text-muted-foreground">SLA:</span>
              {CALENDAR_SLA_BANDS.map((band) => (
                <Button
                  key={band}
                  type="button"
                  size="sm"
                  variant={selectedBands.includes(band) ? "default" : "outline"}
                  onClick={() => toggleBand(band)}
                  aria-pressed={selectedBands.includes(band)}
                  className="gap-2"
                >
                  <span>{SLA_BAND_LABELS[band]}</span>
                  <Badge variant="secondary" className="px-1.5 text-[11px]">
                    {slaSummary[band]}
                  </Badge>
                </Button>
              ))}
            </div>
          ) : null}
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1">
              <label className="text-xs uppercase text-muted-foreground" htmlFor="calendar-person">
                Сотрудник (person_id)
              </label>
              <Input
                id="calendar-person"
                value={personId}
                onChange={(event) => setPersonId(event.target.value)}
                placeholder="UUID сотрудника"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs uppercase text-muted-foreground" htmlFor="calendar-site">
                Объект (site_id)
              </label>
              <Input
                id="calendar-site"
                value={siteId}
                onChange={(event) => setSiteId(event.target.value)}
                placeholder="UUID объекта"
              />
            </div>
            <div className="flex items-end gap-2">
              <Button type="button" onClick={applyFilters} disabled={loading}>
                Применить
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={resetFilters}
                disabled={!filtersActive && selectedSources.length === 0}
              >
                Сбросить
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span>
              Всего событий: <strong className="text-foreground">{total}</strong>
            </span>
            <span>
              Просрочек:{" "}
              <strong className={overdueTotal > 0 ? "text-destructive" : "text-foreground"}>
                {overdueTotal}
              </strong>
            </span>
            {generatedAtLabel ? <span>Сформировано: {generatedAtLabel}</span> : null}
            {includeFact ? (
              <span data-testid="fact-summary">
                Факт зафиксирован: <strong className="text-foreground">{factSummary.withFact}</strong>{" "}
                · опозданий: <strong className="text-destructive">{factSummary.late}</strong> ·
                досрочно: <strong className="text-emerald-600">{factSummary.early}</strong> ·
                в срок: <strong className="text-foreground">{factSummary.onTime}</strong>
              </span>
            ) : null}
            {includeSla ? (
              <span data-testid="sla-summary">
                SLA — просрочено:{" "}
                <strong className="text-destructive">{slaSummary.overdue}</strong> · критично:{" "}
                <strong className="text-orange-600">{slaSummary.critical}</strong> · внимание:{" "}
                <strong className="text-amber-600">{slaSummary.warning}</strong> · в норме:{" "}
                <strong className="text-emerald-600">{slaSummary.ok}</strong>
              </span>
            ) : null}
          </div>
          {icsError ? (
            <div role="alert" className="text-sm text-destructive">
              {icsError}
            </div>
          ) : null}
          <ErrorState error={error ?? undefined} onRetry={() => void load()} />
          {loading ? <LoadingScreen label="Загрузка событий" /> : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState
              title="Событий в календаре нет"
              description="Появятся при создании назначений по медосмотрам, СИЗ, обучению, проверкам, инструктажам и срокам."
            />
          ) : null}
          {!loading && !error && items.length > 0
            ? buckets.map((bucket) => (
                <section key={bucket.key} className="space-y-2">
                  <div className="flex items-center justify-between border-b pb-1">
                    <h3 className="text-sm font-semibold capitalize">{bucket.label}</h3>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">{bucket.items.length}</Badge>
                      {bucket.overdue > 0 ? (
                        <Badge variant="destructive">Просрочек: {bucket.overdue}</Badge>
                      ) : null}
                    </div>
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[180px]">Когда</TableHead>
                        <TableHead>Событие</TableHead>
                        <TableHead className="w-[160px]">Источник</TableHead>
                        <TableHead className="w-[140px]">Статус</TableHead>
                        {includeFact ? (
                          <>
                            <TableHead className="w-[120px]">План</TableHead>
                            <TableHead className="w-[120px]">Факт</TableHead>
                            <TableHead className="w-[120px]">Отклонение</TableHead>
                          </>
                        ) : null}
                        {includeSla ? <TableHead className="w-[200px]">SLA</TableHead> : null}
                        <TableHead className="w-[120px]">Срок</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {bucket.items.map((item) => (
                        <EventRow
                          key={item.id}
                          item={item}
                          includeFact={includeFact}
                          includeSla={includeSla}
                        />
                      ))}
                    </TableBody>
                  </Table>
                </section>
              ))
            : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default CalendarPage;
