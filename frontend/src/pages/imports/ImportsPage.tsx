import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { importsApi, isFeatureDisabledError, isTooManyRowsError } from "@/api/imports";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { BatchesPanel } from "@/features/imports/BatchesPanel";
import { MappingEditor } from "@/features/imports/MappingEditor";
import { PreviewPanel } from "@/features/imports/PreviewPanel";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import type { ImportBatchDto, ImportPreviewDto, ImportTargetDto } from "@/types/dto/imports";

interface ImportsPageData {
  targets: ImportTargetDto[];
  batches: ImportBatchDto[];
}

const INITIAL: ImportsPageData = { targets: [], batches: [] };

/**
 * Мастер импорта (ТЗ разд. 71.1): шаблон → файл → сухой прогон → маппинг → применение.
 *
 * Порядок шагов не декоративный: применение доступно ТОЛЬКО после сухого прогона.
 * Импорт меняет кадровые данные пачками, и «загрузил и сразу применил» — это ровно
 * тот сценарий, ради которого в ТЗ вообще есть dry-run.
 */
const ImportsPage = () => {
  const [targetCode, setTargetCode] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewDto | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  // Файл не влез в синхронную проверку. Держим это отдельным состоянием, а не
  // выводим из размера файла: предел считается в СТРОКАХ, и байты о нём не говорят.
  const [oversized, setOversized] = useState(false);

  const loader = useCallback(async (): Promise<ImportsPageData> => {
    const [targets, batches] = await Promise.all([
      importsApi.targets(),
      importsApi.batches({ limit: 20 })
    ]);
    return { targets, batches };
  }, []);

  const resource = useAsyncResource<ImportsPageData>({
    loader,
    initialData: INITIAL,
    errorMessage: "Не удалось загрузить настройки импорта"
  });

  const target = useMemo(
    () => resource.data.targets.find((item) => item.code === targetCode) ?? null,
    [resource.data.targets, targetCode]
  );

  // Смена цели или файла обесценивает предпросмотр: показывать план, посчитанный
  // для другого файла, — это приглашение применить не то.
  const resetPreview = () => {
    setPreview(null);
    setOverrides({});
    setOversized(false);
  };

  const effectiveMapping = (): Record<string, string> => {
    const base = preview ? { ...preview.mapping } : {};
    for (const [field, header] of Object.entries(overrides)) {
      if (header) base[field] = header;
      else delete base[field];
    }
    return base;
  };

  const runDryRun = async () => {
    if (!target || !file) return;
    setBusy(true);
    try {
      const result = await importsApi.dryRun(target.code, file, preview ? effectiveMapping() : undefined);
      setPreview(result);
      setOversized(false);
    } catch (error) {
      // Слишком большой файл — не ошибка пользователя, а развилка: у такого файла
      // есть фоновый путь, и предложить его здесь честнее, чем оставить с текстом
      // «слишком много строк» и без единого действия.
      if (isTooManyRowsError(error)) setOversized(true);
      // Остальные причины уже показал глобальный обработчик API.
    } finally {
      setBusy(false);
    }
  };

  const runDryRunAsync = async () => {
    if (!target || !file) return;
    setBusy(true);
    try {
      await importsApi.dryRunAsync(target.code, file);
      toast.success("Проверка запущена: результат появится в истории загрузок");
      await resource.reload();
    } catch {
      // Причину уже показал глобальный обработчик API.
    } finally {
      setBusy(false);
    }
  };

  const runApplyAsync = async () => {
    if (!target || !file) return;
    if (
      !window.confirm(
        "Загрузить файл в фоне? Если проверку не запускали, результат станет известен только " +
          "по итогу — загрузку целиком можно будет откатить в истории."
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      await importsApi.applyAsync(target.code, file);
      toast.success("Файл принят: следите за прогрессом в истории загрузок");
      setOversized(false);
      await resource.reload();
    } catch {
      // Причину уже показал глобальный обработчик API.
    } finally {
      setBusy(false);
    }
  };

  const runApply = async () => {
    if (!target || !file || !preview) return;
    const willWrite = (preview.counts.create ?? 0) + (preview.counts.update ?? 0);
    if (willWrite === 0) {
      toast.info("Применять нечего: файл не создаёт и не меняет ни одной записи");
      return;
    }
    if (!window.confirm(`Применить импорт? Будет затронуто записей: ${willWrite}.`)) return;

    setBusy(true);
    try {
      const result = await importsApi.apply(target.code, file, effectiveMapping());
      toast.success(
        `Импорт применён: создано ${result.batch.created_count}, обновлено ${result.batch.updated_count}`
      );
      setPreview(result.preview);
      await resource.reload();
    } catch {
      // Причину уже показал глобальный обработчик API.
    } finally {
      setBusy(false);
    }
  };

  const downloadTemplate = async () => {
    if (!target) return;
    try {
      await importsApi.downloadTemplate(target.code);
    } catch {
      // Причину уже показал глобальный обработчик API.
    }
  };

  if (resource.loading && resource.data.targets.length === 0) return <LoadingScreen />;

  if (resource.error) {
    if (isFeatureDisabledError(resource.error)) {
      return (
        <EmptyState
          title="Импорт данных отключён"
          description="Модуль импорта выключен для этой организации. Обратитесь к администратору платформы."
        />
      );
    }
    return <ErrorState error={resource.error} onRetry={() => void resource.reload()} />;
  }

  return (
    <div className="space-y-6">
      <RegistryPageHeader
        title="Импорт данных"
        description="Загрузка справочников и кадровых данных из Excel, CSV или JSON"
      />

      <section className="space-y-3 rounded-md border p-4">
        <h2 className="text-lg font-medium">1. Что загружаем</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="import-target">Тип данных</Label>
            <select
              id="import-target"
              className="h-9 min-w-64 rounded-md border px-3 text-sm"
              value={targetCode}
              onChange={(event) => {
                setTargetCode(event.target.value);
                resetPreview();
              }}
            >
              <option value="">— выберите —</option>
              {resource.data.targets.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.title}
                </option>
              ))}
            </select>
          </div>
          <Button variant="outline" disabled={!target} onClick={() => void downloadTemplate()}>
            Скачать шаблон
          </Button>
        </div>
        {target ? (
          <p className="text-sm text-muted-foreground">
            {target.description} Повторная загрузка не создаёт дубли — записи опознаются по ключу:{" "}
            {target.natural_keys.join(" либо ")}.
          </p>
        ) : null}
      </section>

      <section className="space-y-3 rounded-md border p-4">
        <h2 className="text-lg font-medium">2. Файл</h2>
        <input
          type="file"
          aria-label="Файл импорта"
          accept=".csv,.xlsx,.json"
          className="text-sm"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            resetPreview();
          }}
        />
        <div>
          <Button disabled={!target || !file || busy} onClick={() => void runDryRun()}>
            Проверить без записи
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Сухой прогон ничего не записывает: он показывает, что будет создано, обновлено и
          отвергнуто.
        </p>

        {oversized ? (
          <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3">
            <p className="text-sm font-medium">Файл слишком большой для предварительной проверки</p>
            <p className="text-sm text-muted-foreground">
              Такой объём обрабатывается в фоне: файл принимается сразу, а ход работы виден в
              истории загрузок ниже. Сначала имеет смысл прогнать проверку — она ничего не
              записывает и покажет, что получится.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy} onClick={() => void runDryRunAsync()}>
                Проверить в фоне
              </Button>
              <Button variant="outline" disabled={busy} onClick={() => void runApplyAsync()}>
                Загрузить в фоне
              </Button>
            </div>
          </div>
        ) : null}
      </section>

      {preview && target ? (
        <>
          <section className="space-y-3 rounded-md border p-4">
            <h2 className="text-lg font-medium">3. Сопоставление колонок</h2>
            <MappingEditor
              columns={target.columns}
              preview={preview}
              overrides={overrides}
              onChange={(field, header) => setOverrides((prev) => ({ ...prev, [field]: header }))}
            />
            <Button variant="outline" disabled={busy} onClick={() => void runDryRun()}>
              Пересчитать с новым сопоставлением
            </Button>
          </section>

          <section className="space-y-3 rounded-md border p-4">
            <h2 className="text-lg font-medium">4. Результат проверки</h2>
            <PreviewPanel preview={preview} />
            <Button disabled={busy} onClick={() => void runApply()}>
              Применить импорт
            </Button>
          </section>
        </>
      ) : null}

      <section className="space-y-3 rounded-md border p-4">
        <h2 className="text-lg font-medium">История загрузок</h2>
        <BatchesPanel
          batches={resource.data.batches}
          onChanged={() => void resource.reload().catch(() => undefined)}
        />
      </section>
    </div>
  );
};

export default ImportsPage;
