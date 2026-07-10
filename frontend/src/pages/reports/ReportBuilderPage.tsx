import { useCallback, useMemo, useState } from "react";

import { reportBuilderApi } from "@/api/reportBuilder";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { usePolling } from "@/hooks/usePolling";
import type {
  ReportColumnMetaDto,
  ReportConfigDto,
  ReportDatasetDto,
  ReportDefinitionDto,
  ReportExportFormat,
  ReportFilterDto,
  ReportPreviewDto
} from "@/types/dto/reportBuilder";

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_TICKS = 40; // ~60 секунд

const JOB_ERROR_LABELS: Record<string, string> = {
  pdf_renderer_unavailable: "PDF-конвертер временно недоступен — попробуйте CSV/XLSX",
  row_limit_exceeded: "Слишком много строк — сузьте фильтры",
  pdf_row_limit_exceeded: "Для PDF слишком много строк — сузьте фильтры или используйте CSV/XLSX",
  definition_missing: "Отчёт был удалён",
  internal_error: "Внутренняя ошибка экспорта — попробуйте ещё раз"
};

type FilterRow = { field: string; op: string; value: string };

type ExportState =
  | { phase: "idle" }
  | { phase: "polling"; jobId: string; format: ReportExportFormat; ticks: number }
  | { phase: "done"; jobId: string; format: ReportExportFormat }
  | { phase: "failed"; message: string };

const EMPTY_DATASETS = { items: [] as ReportDatasetDto[], total: 0 };
const EMPTY_DEFINITIONS = { items: [] as ReportDefinitionDto[], total: 0 };

export default function ReportBuilderPage() {
  const datasetsRes = useAsyncResource<{ items: ReportDatasetDto[]; total: number }>({
    loader: useCallback(() => reportBuilderApi.listDatasets(), []),
    initialData: EMPTY_DATASETS,
    errorMessage: "Не удалось загрузить датасеты"
  });
  const definitionsRes = useAsyncResource<{ items: ReportDefinitionDto[]; total: number }>({
    loader: useCallback(() => reportBuilderApi.listDefinitions(), []),
    initialData: EMPTY_DEFINITIONS,
    errorMessage: "Не удалось загрузить сохранённые отчёты"
  });

  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [datasetCode, setDatasetCode] = useState("");
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [filters, setFilters] = useState<FilterRow[]>([]);
  const [groupBy, setGroupBy] = useState<string[]>([]);
  const [sumField, setSumField] = useState("");
  const [sortField, setSortField] = useState("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ReportPreviewDto | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [exportState, setExportState] = useState<ExportState>({ phase: "idle" });

  const datasets = datasetsRes.data.items;
  const definitions = definitionsRes.data.items;
  const dataset = useMemo(
    () => datasets.find((d) => d.code === datasetCode) ?? null,
    [datasets, datasetCode]
  );
  const columnsByKey = useMemo(() => {
    const map = new Map<string, ReportColumnMetaDto>();
    dataset?.columns.forEach((c) => map.set(c.key, c));
    return map;
  }, [dataset]);

  const resetEditor = useCallback(
    (ds?: string) => {
      setEditingId(null);
      setName("");
      setDescription("");
      setSelectedColumns([]);
      setFilters([]);
      setGroupBy([]);
      setSumField("");
      setSortField("");
      setSortDir("asc");
      setPreview(null);
      setPreviewError(null);
      setSaveError(null);
      setExportState({ phase: "idle" });
      if (ds !== undefined) setDatasetCode(ds);
    },
    []
  );

  const buildConfig = useCallback((): ReportConfigDto => {
    const config: ReportConfigDto = {};
    if (groupBy.length > 0) {
      config.group_by = groupBy;
      config.aggregates = [{ fn: "count" }];
      if (sumField) config.aggregates.push({ fn: "sum", field: sumField });
    } else if (selectedColumns.length > 0) {
      config.columns = selectedColumns;
    }
    const parsed: ReportFilterDto[] = [];
    for (const row of filters) {
      if (!row.field || !row.op) continue;
      const col = columnsByKey.get(row.field);
      if (!col) continue;
      if (row.op !== "in" && row.value.trim() === "") continue; // нет значения — нет фильтра
      let value: unknown = row.value;
      if (col.kind === "number") value = Number(row.value);
      if (col.kind === "bool") value = row.value === "true";
      if (row.op === "in") {
        const values = row.value
          .split(",")
          .map((v) => v.trim())
          .filter(Boolean);
        if (values.length === 0) continue; // пустой in — не отправляем
        value = values;
      }
      parsed.push({ field: row.field, op: row.op as ReportFilterDto["op"], value });
    }
    if (parsed.length > 0) config.filters = parsed;
    // stale sortField (например, после смены колонок/группировки) не отправляем
    const validSortKeys = new Set(
      groupBy.length > 0
        ? [...groupBy, "count", ...(sumField ? [`sum_${sumField}`] : [])]
        : selectedColumns.length > 0
          ? selectedColumns
          : [...columnsByKey.keys()]
    );
    if (sortField && validSortKeys.has(sortField)) config.sort = [{ field: sortField, dir: sortDir }];
    return config;
  }, [columnsByKey, filters, groupBy, selectedColumns, sortDir, sortField, sumField]);

  const loadDefinition = useCallback(
    (def: ReportDefinitionDto, asCopy: boolean) => {
      resetEditor(def.dataset_code);
      setEditingId(asCopy ? null : def.id);
      setName(asCopy ? `${def.name} (копия)` : def.name);
      setDescription(def.description ?? "");
      const cfg = def.config_json ?? {};
      setSelectedColumns(cfg.columns ?? []);
      setGroupBy(cfg.group_by ?? []);
      setSumField(cfg.aggregates?.find((a) => a.fn === "sum")?.field ?? "");
      setSortField(cfg.sort?.[0]?.field ?? "");
      setSortDir(cfg.sort?.[0]?.dir ?? "asc");
      setFilters(
        (cfg.filters ?? []).map((f) => ({
          field: f.field,
          op: f.op,
          value: Array.isArray(f.value) ? f.value.join(",") : String(f.value ?? "")
        }))
      );
    },
    [resetEditor]
  );

  const runPreview = useCallback(async () => {
    if (!datasetCode) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      setPreview(await reportBuilderApi.preview({ dataset_code: datasetCode, config_json: buildConfig() }));
    } catch {
      setPreview(null);
      setPreviewError("Не удалось построить предпросмотр — проверьте фильтры");
    } finally {
      setPreviewLoading(false);
    }
  }, [buildConfig, datasetCode]);

  const saveDefinition = useCallback(async () => {
    if (!datasetCode || !name.trim()) {
      setSaveError("Укажите название и датасет");
      return;
    }
    setSaveError(null);
    const payload = {
      name: name.trim(),
      description: description.trim() || null,
      dataset_code: datasetCode,
      config_json: buildConfig()
    };
    try {
      if (editingId) {
        await reportBuilderApi.updateDefinition(editingId, payload);
      } else {
        const created = await reportBuilderApi.createDefinition(payload);
        setEditingId(created.id);
      }
      await definitionsRes.reload();
    } catch {
      setSaveError("Не удалось сохранить (возможно, имя уже занято)");
    }
  }, [buildConfig, datasetCode, description, definitionsRes, editingId, name]);

  const removeDefinition = useCallback(
    async (def: ReportDefinitionDto) => {
      if (!window.confirm(`Удалить отчёт «${def.name}»?`)) return;
      try {
        await reportBuilderApi.deleteDefinition(def.id);
        if (editingId === def.id) resetEditor("");
        await definitionsRes.reload();
      } catch {
        /* ошибка удаления не блокирует страницу */
      }
    },
    [definitionsRes, editingId, resetEditor]
  );

  const startExport = useCallback(
    async (format: ReportExportFormat) => {
      if (!editingId) return;
      try {
        const { job_id } = await reportBuilderApi.runDefinition(editingId, format);
        setExportState({ phase: "polling", jobId: job_id, format, ticks: 0 });
      } catch {
        setExportState({ phase: "failed", message: "Не удалось запустить экспорт" });
      }
    },
    [editingId]
  );

  // Поллинг job'а экспорта: usePolling даёт in-flight guard и cleanup;
  // callback пересоздаётся на каждый рендер и читает jobId из актуального exportState,
  // поэтому повторный экспорт не может «доехать» результатом старого job'а
  // (терминальные переходы дополнительно защищены сверкой prev.jobId в updater'е).
  usePolling(
    async () => {
      if (exportState.phase !== "polling") return;
      const { jobId, format, ticks } = exportState;
      const job = await reportBuilderApi.getExportJob(jobId);
      if (job.status === "done") {
        setExportState((prev) =>
          prev.phase === "polling" && prev.jobId === jobId ? { phase: "done", jobId, format } : prev
        );
      } else if (job.status === "failed") {
        const code = job.error_payload?.code ?? "";
        setExportState((prev) =>
          prev.phase === "polling" && prev.jobId === jobId
            ? { phase: "failed", message: JOB_ERROR_LABELS[code] ?? "Экспорт не удался — попробуйте ещё раз" }
            : prev
        );
      } else if (ticks + 1 >= POLL_MAX_TICKS) {
        setExportState({ phase: "failed", message: "Экспорт занял слишком много времени" });
      } else {
        setExportState((prev) =>
          prev.phase === "polling" && prev.jobId === jobId ? { ...prev, ticks: prev.ticks + 1 } : prev
        );
      }
    },
    POLL_INTERVAL_MS,
    {
      enabled: exportState.phase === "polling"
      // транзиентную ошибку поллинга хук проглатывает (onError не задан) — ждём следующего тика
    }
  );

  const downloadCurrent = useCallback(async () => {
    if (exportState.phase !== "done") return;
    const def = definitions.find((d) => d.id === editingId);
    await reportBuilderApi.downloadReportExport(
      exportState.jobId,
      `${def?.name ?? "report"}.${exportState.format}`
    );
  }, [definitions, editingId, exportState]);

  if (datasetsRes.loading || definitionsRes.loading) return <LoadingScreen />;
  if (datasetsRes.error) {
    return <ErrorState error={datasetsRes.error} onRetry={() => void datasetsRes.reload()} />;
  }
  if (definitionsRes.error) {
    return <ErrorState error={definitionsRes.error} onRetry={() => void definitionsRes.reload()} />;
  }

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Отчёты", to: "/reports" }, { label: "Конструктор отчётов" }]} />

      <Card>
        <CardHeader>
          <CardTitle>Сохранённые отчёты</CardTitle>
          <CardDescription>Готовые шаблоны и ваши отчёты. Системные шаблоны можно дублировать.</CardDescription>
        </CardHeader>
        <CardContent>
          {definitions.length === 0 ? (
            <EmptyState title="Пока нет отчётов" description="Создайте первый отчёт в конструкторе ниже." />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-4">Название</th>
                  <th className="py-2 pr-4">Датасет</th>
                  <th className="py-2 pr-4" />
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {definitions.map((def) => (
                  <tr key={def.id} className="border-b last:border-0">
                    <td className="py-2 pr-4">
                      {def.name} {def.is_system ? <Badge variant="secondary">Системный</Badge> : null}
                    </td>
                    <td className="py-2 pr-4">
                      {datasets.find((d) => d.code === def.dataset_code)?.title ?? def.dataset_code}
                    </td>
                    <td className="py-2 pr-4">
                      <Button size="sm" variant="outline" onClick={() => loadDefinition(def, false)}>
                        Открыть
                      </Button>{" "}
                      <Button size="sm" variant="outline" onClick={() => loadDefinition(def, true)}>
                        Дублировать
                      </Button>
                    </td>
                    <td className="py-2 text-right">
                      {!def.is_system ? (
                        <Button size="sm" variant="destructive" onClick={() => void removeDefinition(def)}>
                          Удалить
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Конструктор</CardTitle>
          <CardDescription>
            Датасет → колонки → фильтры → группировка → сортировка. Предпросмотр показывает первые 100 строк.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-1">
              <Label htmlFor="rb-name">Название отчёта</Label>
              <Input id="rb-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="rb-description">Описание</Label>
              <Input id="rb-description" value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="rb-dataset">Датасет</Label>
              <select
                id="rb-dataset"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={datasetCode}
                onChange={(e) => resetEditor(e.target.value)}
              >
                <option value="">— выберите —</option>
                {datasets.map((d) => (
                  <option key={d.code} value={d.code}>
                    {d.title}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {dataset ? (
            <>
              {groupBy.length === 0 ? (
                <div className="space-y-1">
                  <Label>Колонки</Label>
                  <div className="flex flex-wrap gap-3">
                    {dataset.columns.map((col) => (
                      <label key={col.key} className="flex items-center gap-1 text-sm">
                        <input
                          type="checkbox"
                          checked={selectedColumns.includes(col.key)}
                          onChange={(e) =>
                            setSelectedColumns((prev) =>
                              e.target.checked ? [...prev, col.key] : prev.filter((k) => k !== col.key)
                            )
                          }
                        />
                        {col.label}
                      </label>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">Ничего не выбрано — будут все колонки.</p>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Включена группировка — выводятся группировочные поля и агрегаты.
                </p>
              )}

              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Label>Фильтры</Label>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setFilters((prev) => [...prev, { field: "", op: "eq", value: "" }])}
                  >
                    Добавить фильтр
                  </Button>
                </div>
                {filters.map((row, idx) => {
                  const col = row.field ? columnsByKey.get(row.field) : undefined;
                  return (
                    <div key={idx} data-testid={`filter-row-${idx}`} className="flex flex-wrap items-end gap-2">
                      <div className="space-y-1">
                        <Label htmlFor={`rb-filter-field-${idx}`}>Поле</Label>
                        <select
                          id={`rb-filter-field-${idx}`}
                          aria-label="Поле"
                          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                          value={row.field}
                          onChange={(e) =>
                            setFilters((prev) =>
                              prev.map((r, i) =>
                                i === idx
                                  ? {
                                      field: e.target.value,
                                      op: columnsByKey.get(e.target.value)?.ops[0] ?? "eq",
                                      value: ""
                                    }
                                  : r
                              )
                            )
                          }
                        >
                          <option value="">— поле —</option>
                          {dataset.columns.map((c) => (
                            <option key={c.key} value={c.key}>
                              {c.label}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor={`rb-filter-op-${idx}`}>Оператор</Label>
                        <select
                          id={`rb-filter-op-${idx}`}
                          aria-label="Оператор"
                          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                          value={row.op}
                          onChange={(e) =>
                            setFilters((prev) => prev.map((r, i) => (i === idx ? { ...r, op: e.target.value } : r)))
                          }
                        >
                          {(col?.ops ?? ["eq"]).map((op) => (
                            <option key={op} value={op}>
                              {op}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor={`rb-filter-value-${idx}`}>Значение</Label>
                        {col?.kind === "enum" && row.op !== "in" ? (
                          <select
                            id={`rb-filter-value-${idx}`}
                            aria-label="Значение"
                            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                            value={row.value}
                            onChange={(e) =>
                              setFilters((prev) => prev.map((r, i) => (i === idx ? { ...r, value: e.target.value } : r)))
                            }
                          >
                            <option value="">—</option>
                            {(col.enum_values ?? []).map((v) => (
                              <option key={v} value={v}>
                                {v}
                              </option>
                            ))}
                          </select>
                        ) : col?.kind === "bool" ? (
                          <select
                            id={`rb-filter-value-${idx}`}
                            aria-label="Значение"
                            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                            value={row.value}
                            onChange={(e) =>
                              setFilters((prev) => prev.map((r, i) => (i === idx ? { ...r, value: e.target.value } : r)))
                            }
                          >
                            <option value="">—</option>
                            <option value="true">да</option>
                            <option value="false">нет</option>
                          </select>
                        ) : (
                          <Input
                            id={`rb-filter-value-${idx}`}
                            aria-label="Значение"
                            type={
                              col?.kind === "number"
                                ? "number"
                                : col?.kind === "date"
                                  ? "date"
                                  : col?.kind === "datetime"
                                    ? "datetime-local"
                                    : "text"
                            }
                            value={row.value}
                            onChange={(e) =>
                              setFilters((prev) => prev.map((r, i) => (i === idx ? { ...r, value: e.target.value } : r)))
                            }
                          />
                        )}
                      </div>
                      <Button size="sm" variant="ghost" onClick={() => setFilters((prev) => prev.filter((_, i) => i !== idx))}>
                        Убрать
                      </Button>
                    </div>
                  );
                })}
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-1">
                  <Label htmlFor="rb-groupby">Группировка</Label>
                  <select
                    id="rb-groupby"
                    className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                    value={groupBy[0] ?? ""}
                    onChange={(e) => setGroupBy(e.target.value ? [e.target.value] : [])}
                  >
                    <option value="">— без группировки —</option>
                    {dataset.columns.map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </div>
                {groupBy.length > 0 ? (
                  <div className="space-y-1">
                    <Label htmlFor="rb-sum">Сумма по</Label>
                    <select
                      id="rb-sum"
                      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={sumField}
                      onChange={(e) => setSumField(e.target.value)}
                    >
                      <option value="">— только количество —</option>
                      {dataset.columns
                        .filter((c) => c.aggregatable)
                        .map((c) => (
                          <option key={c.key} value={c.key}>
                            {c.label}
                          </option>
                        ))}
                    </select>
                  </div>
                ) : null}
                <div className="space-y-1">
                  <Label htmlFor="rb-sort">Сортировка</Label>
                  <div className="flex gap-2">
                    <select
                      id="rb-sort"
                      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={sortField}
                      onChange={(e) => setSortField(e.target.value)}
                    >
                      <option value="">— нет —</option>
                      {(groupBy.length > 0
                        ? [...groupBy, "count", ...(sumField ? [`sum_${sumField}`] : [])]
                        : selectedColumns.length > 0
                          ? selectedColumns
                          : dataset.columns.map((c) => c.key)
                      ).map((key) => (
                        <option key={key} value={key}>
                          {columnsByKey.get(key)?.label ?? key}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Направление сортировки"
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                      value={sortDir}
                      onChange={(e) => setSortDir(e.target.value as "asc" | "desc")}
                    >
                      <option value="asc">по возр.</option>
                      <option value="desc">по убыв.</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => void runPreview()} disabled={previewLoading}>
                  Предпросмотр
                </Button>
                <Button variant="outline" onClick={() => void saveDefinition()}>
                  Сохранить
                </Button>
                {editingId ? (
                  <>
                    <span className="text-sm text-muted-foreground">Экспорт:</span>
                    <Button size="sm" variant="outline" onClick={() => void startExport("csv")}>
                      CSV
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void startExport("xlsx")}>
                      XLSX
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void startExport("pdf")}>
                      PDF
                    </Button>
                  </>
                ) : (
                  <span className="text-xs text-muted-foreground">Сохраните отчёт, чтобы экспортировать.</span>
                )}
              </div>
              {saveError ? (
                <p role="alert" className="text-sm text-destructive">
                  {saveError}
                </p>
              ) : null}
              {exportState.phase === "polling" ? <p className="text-sm text-muted-foreground">Формируем файл…</p> : null}
              {exportState.phase === "done" ? (
                <Button size="sm" onClick={() => void downloadCurrent()}>
                  Скачать
                </Button>
              ) : null}
              {exportState.phase === "failed" ? (
                <p role="alert" className="text-sm text-destructive">
                  {exportState.message}
                </p>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>

      {dataset ? (
        <Card>
          <CardHeader>
            <CardTitle>Предпросмотр</CardTitle>
            {preview ? <CardDescription>Всего: {preview.total}</CardDescription> : null}
          </CardHeader>
          <CardContent>
            {previewError ? (
              <p role="alert" className="text-sm text-destructive">
                {previewError}
              </p>
            ) : null}
            {preview && preview.rows.length === 0 && !previewError ? (
              <EmptyState title="Нет данных" description="Под текущие фильтры не попало ни одной строки." />
            ) : null}
            {preview && preview.rows.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      {preview.columns.map((c) => (
                        <th key={c.key} className="py-2 pr-4">
                          {c.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, i) => (
                      <tr key={i} className="border-b last:border-0">
                        {preview.columns.map((c) => (
                          <td key={c.key} className="py-2 pr-4">
                            {row[c.key] === null || row[c.key] === undefined
                              ? "—"
                              : typeof row[c.key] === "boolean"
                                ? row[c.key]
                                  ? "да"
                                  : "нет"
                                : String(row[c.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
