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
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import {
  CALENDAR_SLA_BANDS,
  CALENDAR_SOURCE_TYPES,
  type CalendarEventItemDto,
  type CalendarEventsResponseDto,
  type CalendarSavedViewDto,
  type CalendarSavedViewPayloadDto,
  type CalendarSavedViewWriteRequest,
  type CalendarSlaBand,
  type CalendarSourceCountDto,
  type CalendarSourceType,
} from "@/types/dto/calendar";
import { downloadBlob } from "@/utils/download";

type CalendarView = "day" | "week" | "month" | "year" | "list";

const VIEWS: { value: CalendarView; label: string }[] = [
  { value: "day", label: "День" },
  { value: "week", label: "Неделя" },
  { value: "month", label: "Месяц" },
  { value: "year", label: "Год" },
  { value: "list", label: "Список" },
];

const SOURCE_LABELS: Record<CalendarSourceType, string> = {
  medical_exam: "Медосмотры",
  // Подписи не было вовсе: источник отдавался бэкендом, но отсутствовал в
  // CalendarSourceType, поэтому строка направления рисовалась без названия.
  medical_referral: "Направления на медосмотр",
  ppe_issue: "СИЗ",
  permit: "Допуски",
  training_session: "Обучение",
  inspection: "Проверки",
  compliance_deadline: "Контрольные сроки",
  briefing_entry: "Инструктажи",
  calendar_event: "Прочие события",
  // Доп. №1 разд. 55.3 «экологический календарь».
  ecology_permit: "Экология: разрешения",
  ecology_measurement: "Экология: замеры ПЭК",
};

const DRILL_DOWN: Partial<Record<CalendarSourceType, string>> = {
  medical_exam: "/medical",
  ppe_issue: "/ppe",
  permit: "/persons",
  training_session: "/training",
  inspection: "/inspections",
  compliance_deadline: "/workspace/data-quality",
  ecology_permit: "/ecology",
  ecology_measurement: "/ecology",
  briefing_entry: "/briefings",
};

const SLA_BAND_LABELS: Record<CalendarSlaBand, string> = {
  overdue: "Просрочено",
  critical: "Критично",
  warning: "Внимание",
  ok: "В норме",
};

type LoadDimension = "person" | "site";

const LOAD_DIM_LABELS: Record<LoadDimension, string> = {
  person: "По людям",
  site: "По объектам",
};

const isCalendarSource = (value: string): value is CalendarSourceType =>
  (CALENDAR_SOURCE_TYPES as readonly string[]).includes(value);

const isSlaBand = (value: string): value is CalendarSlaBand =>
  (CALENDAR_SLA_BANDS as readonly string[]).includes(value);

const isView = (value: string | null): value is CalendarView =>
  value === "day" ||
  value === "week" ||
  value === "month" ||
  value === "year" ||
  value === "list";

const isLoadDim = (value: string | null): value is LoadDimension =>
  value === "person" || value === "site";

const loadCellClass = (count: number): string => {
  if (count === 0) return "bg-transparent text-muted-foreground";
  if (count === 1) return "bg-blue-100 text-blue-900";
  if (count <= 3) return "bg-blue-300 text-blue-950";
  if (count <= 6) return "bg-blue-500 text-white";
  return "bg-blue-700 text-white";
};

const truncateId = (value: string): string =>
  value.length > 10 ? `${value.slice(0, 8)}…` : value;

const parseSources = (raw: string | null): CalendarSourceType[] => {
  if (!raw) return [];
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter(
      (part) => part.length > 0 && isCalendarSource(part),
    ) as CalendarSourceType[];
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
  if (view === "day")
    return new Date(key).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  if (view === "week") {
    const start = new Date(key);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    return `Неделя ${start.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" })} — ${end.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" })}`;
  }
  if (view === "month")
    return new Date(key).toLocaleDateString("ru-RU", {
      month: "long",
      year: "numeric",
    });
  if (view === "year")
    return new Date(key).toLocaleDateString("ru-RU", { year: "numeric" });
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
    minute: "2-digit",
  });
};

const formatDateOnly = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
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
  count,
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
    <Badge
      variant={selected ? "secondary" : "outline"}
      className="px-1.5 text-[11px]"
    >
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
  ok: "border-transparent bg-emerald-500 text-white",
};

const SlaBadge = ({ band }: { band: CalendarSlaBand }) => (
  <Badge
    variant="outline"
    className={SLA_BAND_BADGE_CLASS[band]}
    data-sla-band={band}
  >
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

type HeatmapCell = { count: number; overdue: number };
type HeatmapRow = {
  entityId: string;
  cells: HeatmapCell[];
  total: number;
  overdueTotal: number;
};
type HeatmapData = {
  rows: HeatmapRow[];
  bucketKeys: string[];
  bucketLabels: string[];
};

const buildHeatmap = (
  items: CalendarEventItemDto[],
  view: CalendarView,
  dimension: LoadDimension,
): HeatmapData => {
  const rowMap = new Map<string, Map<string, HeatmapCell>>();
  const bucketSet = new Set<string>();
  items.forEach((item) => {
    const entityId = dimension === "person" ? item.person_id : item.site_id;
    if (!entityId) return;
    const bucketKey = bucketKeyFor(view, item.starts_at);
    bucketSet.add(bucketKey);
    const row = rowMap.get(entityId) ?? new Map<string, HeatmapCell>();
    const cell = row.get(bucketKey) ?? { count: 0, overdue: 0 };
    cell.count += 1;
    if (item.is_overdue) cell.overdue += 1;
    row.set(bucketKey, cell);
    rowMap.set(entityId, row);
  });
  const bucketKeys = [...bucketSet].sort();
  const bucketLabels = bucketKeys.map((key) => formatBucketLabel(view, key));
  const rows: HeatmapRow[] = [...rowMap.entries()]
    .map(([entityId, cellMap]) => {
      const cells = bucketKeys.map(
        (key) => cellMap.get(key) ?? { count: 0, overdue: 0 },
      );
      const total = cells.reduce((sum, c) => sum + c.count, 0);
      const overdueTotal = cells.reduce((sum, c) => sum + c.overdue, 0);
      return { entityId, cells, total, overdueTotal };
    })
    .sort((a, b) => b.total - a.total || a.entityId.localeCompare(b.entityId));
  return { rows, bucketKeys, bucketLabels };
};

const ResourceLoadHeatmap = ({
  items,
  view,
  dimension,
  onChangeDimension,
}: {
  items: CalendarEventItemDto[];
  view: CalendarView;
  dimension: LoadDimension;
  onChangeDimension: (dim: LoadDimension) => void;
}) => {
  const data = useMemo(
    () => buildHeatmap(items, view, dimension),
    [items, view, dimension],
  );

  return (
    <section className="space-y-2" data-testid="resource-load-section">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-1">
        <h3 className="text-sm font-semibold">Загрузка ресурсов</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase text-muted-foreground">
            Группировка:
          </span>
          {(["person", "site"] as LoadDimension[]).map((dim) => (
            <Button
              key={dim}
              type="button"
              size="sm"
              variant={dimension === dim ? "default" : "outline"}
              onClick={() => onChangeDimension(dim)}
              aria-pressed={dimension === dim}
            >
              {LOAD_DIM_LABELS[dim]}
            </Button>
          ))}
        </div>
      </div>
      {data.rows.length === 0 ? (
        <div
          data-testid="resource-load-empty"
          className="rounded border border-dashed p-4 text-sm text-muted-foreground"
        >
          Нет данных для тепловой карты загрузки. У событий должен быть заполнен{" "}
          {dimension === "person" ? "person_id" : "site_id"}.
        </div>
      ) : (
        <div className="overflow-x-auto" data-testid="resource-load-heatmap">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[180px]">
                  {dimension === "person" ? "Сотрудник" : "Объект"}
                </TableHead>
                {data.bucketLabels.map((label, idx) => (
                  <TableHead
                    key={data.bucketKeys[idx]}
                    className="text-center whitespace-nowrap"
                  >
                    {label}
                  </TableHead>
                ))}
                <TableHead className="w-[80px] text-center">Всего</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((row) => (
                <TableRow
                  key={row.entityId}
                  data-load-entity={row.entityId}
                  data-load-total={row.total}
                  data-load-overdue-total={row.overdueTotal}
                >
                  <TableCell
                    className="font-mono text-xs text-muted-foreground"
                    title={row.entityId}
                  >
                    {truncateId(row.entityId)}
                  </TableCell>
                  {row.cells.map((cell, idx) => (
                    <TableCell
                      key={data.bucketKeys[idx]}
                      className={`text-center ${loadCellClass(cell.count)}`}
                      data-load-count={cell.count}
                      data-load-overdue={cell.overdue}
                      title={
                        cell.count === 0
                          ? "Нет событий"
                          : `События: ${cell.count}${cell.overdue > 0 ? `, просрочек: ${cell.overdue}` : ""}`
                      }
                    >
                      {cell.count === 0 ? "·" : cell.count}
                    </TableCell>
                  ))}
                  <TableCell className="text-center font-semibold">
                    {row.total}
                    {row.overdueTotal > 0 ? (
                      <span className="ml-1 text-xs text-destructive">
                        ({row.overdueTotal})
                      </span>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
};

const EventRow = ({
  item,
  includeFact,
  includeSla,
}: {
  item: CalendarEventItemDto;
  includeFact: boolean;
  includeSla: boolean;
}) => {
  const link = buildDrillDown(item);
  return (
    <TableRow>
      <TableCell className="text-sm">
        {formatDateTime(item.starts_at)}
      </TableCell>
      <TableCell className="text-sm font-medium">
        {link ? (
          <Link
            to={link}
            className="text-primary underline-offset-4 hover:underline"
          >
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
          <TableCell className="text-sm">
            {formatDateOnly(item.expected_at)}
          </TableCell>
          <TableCell className="text-sm">
            {formatDateOnly(item.actual_at)}
          </TableCell>
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
            {item.sla_band ? (
              <SlaBadge band={item.sla_band} />
            ) : (
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
  const initialView = isView(searchParams.get("view"))
    ? (searchParams.get("view") as CalendarView)
    : "month";
  const initialSources = parseSources(searchParams.get("sources"));
  const initialPersonId = searchParams.get("person_id") ?? "";
  const initialSiteId = searchParams.get("site_id") ?? "";
  const initialIncludeFact = searchParams.get("include_fact") === "1";
  const initialIncludeSla = searchParams.get("include_sla") === "1";
  const initialSlaBands = parseSlaBands(searchParams.get("sla_bands"));
  const initialIncludeLoad = searchParams.get("include_load") === "1";
  const initialLoadDim: LoadDimension = isLoadDim(searchParams.get("load_dim"))
    ? (searchParams.get("load_dim") as LoadDimension)
    : "person";

  const [view, setView] = useState<CalendarView>(initialView);
  const [selectedSources, setSelectedSources] =
    useState<CalendarSourceType[]>(initialSources);
  const [personId, setPersonId] = useState(initialPersonId);
  const [siteId, setSiteId] = useState(initialSiteId);
  const [appliedPersonId, setAppliedPersonId] = useState(initialPersonId);
  const [appliedSiteId, setAppliedSiteId] = useState(initialSiteId);
  const [includeFact, setIncludeFact] = useState(initialIncludeFact);
  const [includeSla, setIncludeSla] = useState(
    initialIncludeSla || initialSlaBands.length > 0,
  );
  const [selectedBands, setSelectedBands] =
    useState<CalendarSlaBand[]>(initialSlaBands);
  const [includeLoad, setIncludeLoad] = useState(initialIncludeLoad);
  const [loadDim, setLoadDim] = useState<LoadDimension>(initialLoadDim);

  const [response, setResponse] = useState<CalendarEventsResponseDto | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [icsLoading, setIcsLoading] = useState(false);
  const [icsError, setIcsError] = useState<string | null>(null);

  const [savedViews, setSavedViews] = useState<CalendarSavedViewDto[]>([]);
  const [savedViewsLoaded, setSavedViewsLoaded] = useState(false);
  const [savedViewsError, setSavedViewsError] = useState<string | null>(null);
  const [appliedViewId, setAppliedViewId] = useState<string | null>(null);
  const [savingView, setSavingView] = useState(false);

  const updateQueryParams = useCallback(
    (patch: {
      view?: CalendarView;
      sources?: CalendarSourceType[];
      person_id?: string;
      site_id?: string;
      include_fact?: boolean;
      include_sla?: boolean;
      sla_bands?: CalendarSlaBand[];
      include_load?: boolean;
      load_dim?: LoadDimension;
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
      if (patch.include_load !== undefined) {
        if (patch.include_load) next.set("include_load", "1");
        else next.delete("include_load");
      }
      if (patch.load_dim !== undefined) {
        if (patch.load_dim === "person") next.delete("load_dim");
        else next.set("load_dim", patch.load_dim);
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
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
        include_sla: includeSla || undefined,
      });
      setResponse(data);
    } catch (nextError) {
      setError(
        (nextError as ApiError) ?? {
          status: 0,
          message: "Не удалось загрузить календарь",
          field_errors: [],
        },
      );
    } finally {
      setLoading(false);
    }
  }, [
    selectedSources,
    appliedPersonId,
    appliedSiteId,
    includeFact,
    includeSla,
  ]);

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
    [updateQueryParams],
  );

  const changeView = useCallback(
    (next: CalendarView) => {
      setView(next);
      updateQueryParams({ view: next });
    },
    [updateQueryParams],
  );

  const applyFilters = useCallback(() => {
    setAppliedPersonId(personId.trim());
    setAppliedSiteId(siteId.trim());
    updateQueryParams({
      person_id: personId.trim(),
      site_id: siteId.trim(),
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
    setIncludeLoad(false);
    setLoadDim("person");
    updateQueryParams({
      sources: [],
      person_id: "",
      site_id: "",
      include_fact: false,
      include_sla: false,
      sla_bands: [],
      include_load: false,
      load_dim: "person",
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
    [updateQueryParams],
  );

  const toggleLoad = useCallback(() => {
    setIncludeLoad((current) => {
      const next = !current;
      updateQueryParams({ include_load: next });
      return next;
    });
  }, [updateQueryParams]);

  const changeLoadDim = useCallback(
    (dim: LoadDimension) => {
      setLoadDim(dim);
      updateQueryParams({ load_dim: dim });
    },
    [updateQueryParams],
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
        include_sla: includeSla || undefined,
      });
      const today = new Date().toISOString().slice(0, 10);
      downloadBlob(blob, `calendar-${today}.ics`);
    } catch (nextError) {
      const message =
        (nextError as ApiError | undefined)?.message ??
        "Не удалось скачать .ics";
      setIcsError(message);
    } finally {
      setIcsLoading(false);
    }
  }, [
    selectedSources,
    appliedPersonId,
    appliedSiteId,
    includeFact,
    includeSla,
  ]);

  // --- Saved views (vNext-CAL-01 / Phase 4.1 — saved filters) ---

  const currentViewPayload = useMemo<CalendarSavedViewPayloadDto>(
    () => ({
      view,
      sources: selectedSources,
      person_id: appliedPersonId || null,
      site_id: appliedSiteId || null,
      include_fact: includeFact,
      include_sla: includeSla,
      sla_bands: selectedBands,
      include_load: includeLoad,
      load_dim: includeLoad ? loadDim : null,
    }),
    [
      view,
      selectedSources,
      appliedPersonId,
      appliedSiteId,
      includeFact,
      includeSla,
      selectedBands,
      includeLoad,
      loadDim,
    ],
  );

  const loadSavedViews = useCallback(async () => {
    try {
      const list = await calendarApi.listSavedViews();
      setSavedViews(list);
      setSavedViewsError(null);
    } catch (nextError) {
      const message =
        (nextError as ApiError | undefined)?.message ??
        "Не удалось загрузить сохранённые фильтры";
      setSavedViewsError(message);
    } finally {
      setSavedViewsLoaded(true);
    }
  }, []);

  useEffect(() => {
    void loadSavedViews();
  }, [loadSavedViews]);

  const applySavedView = useCallback(
    (saved: CalendarSavedViewDto) => {
      const payload = saved.payload;
      const nextView: CalendarView =
        payload.view && isView(payload.view)
          ? (payload.view as CalendarView)
          : "month";
      const nextSources = (payload.sources ?? []).filter((source) =>
        (CALENDAR_SOURCE_TYPES as readonly string[]).includes(source),
      ) as CalendarSourceType[];
      const nextBands = (payload.sla_bands ?? []).filter((band) =>
        (CALENDAR_SLA_BANDS as readonly string[]).includes(band),
      ) as CalendarSlaBand[];
      const nextLoadDim: LoadDimension =
        payload.load_dim && isLoadDim(payload.load_dim)
          ? (payload.load_dim as LoadDimension)
          : "person";
      const nextPersonId = payload.person_id ?? "";
      const nextSiteId = payload.site_id ?? "";

      setView(nextView);
      setSelectedSources(nextSources);
      setPersonId(nextPersonId);
      setSiteId(nextSiteId);
      setAppliedPersonId(nextPersonId);
      setAppliedSiteId(nextSiteId);
      setIncludeFact(Boolean(payload.include_fact));
      setIncludeSla(Boolean(payload.include_sla) || nextBands.length > 0);
      setSelectedBands(nextBands);
      setIncludeLoad(Boolean(payload.include_load));
      setLoadDim(nextLoadDim);
      setAppliedViewId(saved.id);

      updateQueryParams({
        view: nextView,
        sources: nextSources,
        person_id: nextPersonId,
        site_id: nextSiteId,
        include_fact: Boolean(payload.include_fact),
        include_sla: Boolean(payload.include_sla) || nextBands.length > 0,
        sla_bands: nextBands,
        include_load: Boolean(payload.include_load),
        load_dim: nextLoadDim,
      });
    },
    [updateQueryParams],
  );

  const handleSaveCurrentView = useCallback(async () => {
    if (typeof window === "undefined") return;
    const name = window.prompt("Название фильтра");
    const trimmed = name?.trim() ?? "";
    if (!trimmed) return;

    setSavingView(true);
    setSavedViewsError(null);
    try {
      const request: CalendarSavedViewWriteRequest = {
        name: trimmed,
        payload: currentViewPayload,
      };
      const created = await calendarApi.createSavedView(request);
      setSavedViews((current) => {
        const next = [...current, created];
        next.sort((a, b) => (a.created_at < b.created_at ? -1 : 1));
        return next;
      });
      setAppliedViewId(created.id);
    } catch (nextError) {
      const apiError = nextError as ApiError | undefined;
      const message =
        apiError?.status === 409
          ? `Фильтр с именем «${trimmed}» уже существует`
          : (apiError?.message ?? "Не удалось сохранить фильтр");
      setSavedViewsError(message);
    } finally {
      setSavingView(false);
    }
  }, [currentViewPayload]);

  const handleDeleteSavedView = useCallback(async (id: string) => {
    if (typeof window !== "undefined") {
      const ok = window.confirm("Удалить сохранённый фильтр?");
      if (!ok) return;
    }
    setSavedViewsError(null);
    try {
      await calendarApi.deleteSavedView(id);
      setSavedViews((current) => current.filter((entry) => entry.id !== id));
      setAppliedViewId((current) => (current === id ? null : current));
    } catch (nextError) {
      const message =
        (nextError as ApiError | undefined)?.message ??
        "Не удалось удалить фильтр";
      setSavedViewsError(message);
    }
  }, []);

  const items = useMemo(() => {
    const all = response?.items ?? [];
    if (!includeSla || selectedBands.length === 0) return all;
    return all.filter(
      (item) => item.sla_band && selectedBands.includes(item.sla_band),
    );
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
        overdue: list.filter((entry) => entry.is_overdue).length,
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
    return all.reduce(
      (acc, item) => {
        if (item.sla_band && item.sla_band in acc) {
          acc[item.sla_band] += 1;
        }
        return acc;
      },
      { ...empty },
    );
  }, [includeSla, response]);

  const counts = response?.by_source ?? [];
  const total = response?.total ?? 0;
  const overdueTotal = response?.overdue_count ?? 0;
  const generatedAtLabel = response?.generated_at
    ? formatDateTime(response.generated_at)
    : null;
  const filtersActive =
    selectedSources.length > 0 ||
    appliedPersonId.length > 0 ||
    appliedSiteId.length > 0 ||
    includeFact ||
    includeSla ||
    selectedBands.length > 0 ||
    includeLoad;

  return (
    <div className="space-y-4">
      <Breadcrumb
        items={[
          { label: "Главная", to: "/dashboard" },
          { label: "Умный календарь" },
        ]}
      />
      <Card>
        <CardHeader className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <CardTitle>Умный календарь</CardTitle>
            <CardDescription>
              Сводный поток медосмотров, СИЗ, допусков, обучений, проверок,
              контрольных сроков и инструктажей с подсветкой просрочек и
              сравнением план/факт.
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
              variant={includeLoad ? "default" : "outline"}
              size="sm"
              onClick={toggleLoad}
              aria-pressed={includeLoad}
            >
              {includeLoad ? "Скрыть загрузку" : "Показать загрузку"}
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
            <span className="text-xs uppercase text-muted-foreground">
              Вид:
            </span>
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
          <div
            className="flex flex-wrap items-center gap-2"
            data-testid="saved-views-toolbar"
          >
            <span className="text-xs uppercase text-muted-foreground">
              Мои фильтры:
            </span>
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={appliedViewId ?? ""}
              onChange={(event) => {
                const id = event.target.value;
                if (!id) {
                  setAppliedViewId(null);
                  return;
                }
                const target = savedViews.find((entry) => entry.id === id);
                if (target) applySavedView(target);
              }}
              disabled={!savedViewsLoaded}
              aria-label="Мои фильтры"
              data-testid="saved-views-select"
            >
              <option value="">
                {savedViewsLoaded
                  ? savedViews.length === 0
                    ? "— нет сохранённых —"
                    : "— выбрать —"
                  : "Загрузка…"}
              </option>
              {savedViews.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.name}
                </option>
              ))}
            </select>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => void handleSaveCurrentView()}
              disabled={savingView}
              data-testid="saved-views-save"
            >
              {savingView ? "Сохранение…" : "Сохранить как…"}
            </Button>
            {appliedViewId ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => void handleDeleteSavedView(appliedViewId)}
                data-testid="saved-views-delete"
              >
                Удалить
              </Button>
            ) : null}
            {savedViewsError ? (
              <span
                role="alert"
                className="text-sm text-destructive"
                data-testid="saved-views-error"
              >
                {savedViewsError}
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {CALENDAR_SOURCE_TYPES.map((sourceType) => {
              const summary = counts.find(
                (entry) => entry.source_type === sourceType,
              ) ?? {
                source_type: sourceType,
                count: 0,
                overdue_count: 0,
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
            <div
              className="flex flex-wrap items-center gap-2"
              data-testid="sla-band-filter"
            >
              <span className="text-xs uppercase text-muted-foreground">
                SLA:
              </span>
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
              <label
                className="text-xs uppercase text-muted-foreground"
                htmlFor="calendar-person"
              >
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
              <label
                className="text-xs uppercase text-muted-foreground"
                htmlFor="calendar-site"
              >
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
              Всего событий:{" "}
              <strong className="text-foreground">{total}</strong>
            </span>
            <span>
              Просрочек:{" "}
              <strong
                className={
                  overdueTotal > 0 ? "text-destructive" : "text-foreground"
                }
              >
                {overdueTotal}
              </strong>
            </span>
            {generatedAtLabel ? (
              <span>Сформировано: {generatedAtLabel}</span>
            ) : null}
            {includeFact ? (
              <span data-testid="fact-summary">
                Факт зафиксирован:{" "}
                <strong className="text-foreground">
                  {factSummary.withFact}
                </strong>{" "}
                · опозданий:{" "}
                <strong className="text-destructive">{factSummary.late}</strong>{" "}
                · досрочно:{" "}
                <strong className="text-emerald-600">
                  {factSummary.early}
                </strong>{" "}
                · в срок:{" "}
                <strong className="text-foreground">
                  {factSummary.onTime}
                </strong>
              </span>
            ) : null}
            {includeSla ? (
              <span data-testid="sla-summary">
                SLA — просрочено:{" "}
                <strong className="text-destructive">
                  {slaSummary.overdue}
                </strong>{" "}
                · критично:{" "}
                <strong className="text-orange-600">
                  {slaSummary.critical}
                </strong>{" "}
                · внимание:{" "}
                <strong className="text-amber-600">{slaSummary.warning}</strong>{" "}
                · в норме:{" "}
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
          {!loading && !error && includeLoad ? (
            <ResourceLoadHeatmap
              items={items}
              view={view}
              dimension={loadDim}
              onChangeDimension={changeLoadDim}
            />
          ) : null}
          {!loading && !error && items.length > 0
            ? buckets.map((bucket) => (
                <section key={bucket.key} className="space-y-2">
                  <div className="flex items-center justify-between border-b pb-1">
                    <h3 className="text-sm font-semibold capitalize">
                      {bucket.label}
                    </h3>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">{bucket.items.length}</Badge>
                      {bucket.overdue > 0 ? (
                        <Badge variant="destructive">
                          Просрочек: {bucket.overdue}
                        </Badge>
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
                            <TableHead className="w-[120px]">
                              Отклонение
                            </TableHead>
                          </>
                        ) : null}
                        {includeSla ? (
                          <TableHead className="w-[200px]">SLA</TableHead>
                        ) : null}
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
