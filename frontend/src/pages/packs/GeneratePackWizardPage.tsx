import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  CheckCircle,
  ChevronRight,
  ClipboardList,
  Play,
  Settings2,
  Upload,
} from "lucide-react";
import { toast } from "sonner";

import { packsApi } from "@/api/packs";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import type { ApiError } from "@/types/dto/common";

interface Preset {
  id: string;
  code: string;
  name: string;
  status: string;
}

const WIZARD_STEPS = [
  { step: 1, label: "Пресет", icon: ClipboardList },
  { step: 2, label: "Данные строк", icon: Upload },
  { step: 3, label: "Параметры", icon: Settings2 },
  { step: 4, label: "Запуск", icon: Play },
  { step: 5, label: "Результат", icon: CheckCircle },
];

const DEFAULT_ROWS_JSON = '[{"doc":"Акт","employee":"Иванов И.И."}]';

const GeneratePackWizardPage = () => {
  const { presetId: presetIdParam = "" } = useParams();
  const navigate = useNavigate();

  const [initialIdempotencyKey, setInitialIdempotencyKey] = useState(
    () => `wizard-${Date.now()}`,
  );
  const [step, setStep] = useState(presetIdParam ? 2 : 1);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [presetsLoading, setPresetsLoading] = useState(false);
  const [presetsError, setPresetsError] = useState<ApiError | null>(null);
  const [selectedPresetId, setSelectedPresetId] = useState(presetIdParam);
  const [rowsJson, setRowsJson] = useState(DEFAULT_ROWS_JSON);
  const rowsJsonRef = useRef(DEFAULT_ROWS_JSON);
  const [rowsEditorKey, setRowsEditorKey] = useState(0);
  const [rowsDirty, setRowsDirty] = useState(false);
  const [rowsError, setRowsError] = useState<string | null>(null);
  const [rowsCount, setRowsCount] = useState<number | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState(initialIdempotencyKey);
  const [dryRun, setDryRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [packRunId, setPackRunId] = useState<string | null>(null);
  const [runError, setRunError] = useState<ApiError | null>(null);
  const [draftOrigin, setDraftOrigin] = useState(() => ({
    step: presetIdParam ? 2 : 1,
    selectedPresetId: presetIdParam,
    idempotencyKey: initialIdempotencyKey,
    dryRun: false,
  }));

  const loadPresets = async () => {
    setPresetsLoading(true);
    setPresetsError(null);
    try {
      const data = await packsApi.getPresets<Preset>();
      setPresets(data);
    } catch (err) {
      setPresetsError(
        (err as ApiError) ?? { message: "Не удалось загрузить пресеты" },
      );
    } finally {
      setPresetsLoading(false);
    }
  };

  const hasUnsavedChanges = useMemo(() => {
    if (packRunId) {
      return false;
    }
    return (
      step !== draftOrigin.step ||
      selectedPresetId !== draftOrigin.selectedPresetId ||
      rowsDirty ||
      idempotencyKey !== draftOrigin.idempotencyKey ||
      dryRun !== draftOrigin.dryRun
    );
  }, [
    draftOrigin,
    dryRun,
    idempotencyKey,
    packRunId,
    rowsDirty,
    selectedPresetId,
    step,
  ]);

  useUnsavedChanges(hasUnsavedChanges);

  useEffect(() => {
    if (presetIdParam) return;
    void loadPresets();
  }, [presetIdParam]);

  const validateRows = (): Array<Record<string, unknown>> | null => {
    const source = rowsJsonRef.current;
    try {
      const parsed = JSON.parse(source) as unknown;
      if (!Array.isArray(parsed)) {
        setRowsError("Данные должны быть массивом JSON");
        return null;
      }
      setRowsJson(source);
      setRowsDirty(false);
      setRowsCount(parsed.length);
      setRowsError(null);
      return parsed as Array<Record<string, unknown>>;
    } catch {
      setRowsError("Невалидный JSON");
      return null;
    }
  };

  const runPack = async () => {
    const rows = validateRows();
    if (!rows || !selectedPresetId) return;
    setRunning(true);
    setRunError(null);
    try {
      const response = await packsApi.createRun(
        selectedPresetId,
        rows,
        dryRun,
        idempotencyKey,
      );
      setPackRunId(response.pack_run_id);
      toast.success(dryRun ? "Dry-run запущен" : "Пакет поставлен в очередь");
      setStep(5);
    } catch (err) {
      setRunError(
        (err as ApiError) ?? { message: "Не удалось запустить генерацию" },
      );
    } finally {
      setRunning(false);
    }
  };

  const selectedPreset = presets.find((p) => p.id === selectedPresetId);

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Главная", to: "/dashboard" },
          { label: "Пресеты", to: "/package-presets" },
          { label: "Мастер генерации" },
        ]}
      />

      {/* Step indicators */}
      <div className="flex flex-wrap gap-2">
        {WIZARD_STEPS.map(({ step: s, label, icon: Icon }) => (
          <div
            key={s}
            className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${
              step === s
                ? "border-primary bg-primary text-primary-foreground"
                : step > s
                  ? "border-green-500 text-green-600"
                  : "border-muted-foreground/30 text-muted-foreground"
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </div>
        ))}
      </div>

      {/* Step 1: Select preset */}
      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle>Шаг 1 — Выбор пресета</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <ErrorState
              error={presetsError ?? undefined}
              onRetry={() => void loadPresets()}
            />
            {presetsLoading ? (
              <div className="text-sm text-muted-foreground">
                Загрузка пресетов…
              </div>
            ) : presets.length === 0 && !presetsError ? (
              <EmptyState
                title="Пресеты не найдены"
                description="Создайте пресет в разделе «Пресеты пакетов», затем вернитесь сюда."
              />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {presets
                  .filter((p) => p.status === "active")
                  .map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setSelectedPresetId(p.id)}
                      className={`rounded-lg border p-4 text-left transition hover:border-primary ${
                        selectedPresetId === p.id
                          ? "border-primary bg-primary/5"
                          : ""
                      }`}
                    >
                      <div className="font-medium">{p.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {p.code}
                      </div>
                    </button>
                  ))}
              </div>
            )}
            <Button disabled={!selectedPresetId} onClick={() => setStep(2)}>
              Далее <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Input rows */}
      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle>Шаг 2 — Данные строк (JSON)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {selectedPreset && (
              <div className="rounded-md bg-muted/40 px-3 py-2 text-sm">
                Пресет: <strong>{selectedPreset.name}</strong> (
                {selectedPreset.code})
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="rows-json">Массив строк в формате JSON</Label>
              <textarea
                key={rowsEditorKey}
                id="rows-json"
                className="min-h-48 w-full rounded-md border border-input bg-background p-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                defaultValue={rowsJson}
                onChange={(e) => {
                  rowsJsonRef.current = e.target.value;
                  if (!rowsDirty) {
                    setRowsDirty(true);
                  }
                }}
                placeholder='[{"doc": "Инструкция", "employee": "Иванов И.И."}]'
              />
              {rowsError && (
                <p className="text-sm text-destructive">{rowsError}</p>
              )}
              <p className="text-xs text-muted-foreground">
                Каждый объект массива соответствует одной строке (одному
                документу). Ключи должны совпадать с полями маппинга пресета.
              </p>
            </div>
            <div className="flex gap-2">
              {!presetIdParam && (
                <Button variant="outline" onClick={() => setStep(1)}>
                  Назад
                </Button>
              )}
              <Button
                onClick={() => {
                  const rows = validateRows();
                  if (rows) setStep(3);
                }}
              >
                Далее <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Options */}
      {step === 3 && (
        <Card>
          <CardHeader>
            <CardTitle>Шаг 3 — Параметры запуска</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="idempotency-key">
                Ключ идемпотентности (уникальный запуск)
              </Label>
              <Input
                id="idempotency-key"
                value={idempotencyKey}
                onChange={(e) => setIdempotencyKey(e.target.value)}
                placeholder="метка-времени мастера"
              />
              <p className="text-xs text-muted-foreground">
                Повторный запрос с тем же ключом вернёт результат первого
                запуска.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <input
                id="dry-run"
                type="checkbox"
                className="h-4 w-4 rounded border-input"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
              />
              <Label htmlFor="dry-run" className="cursor-pointer">
                Dry-run (предварительная проверка без записи результатов)
              </Label>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(2)}>
                Назад
              </Button>
              <Button
                disabled={!idempotencyKey.trim()}
                onClick={() => setStep(4)}
              >
                Далее <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 4: Confirm & Run */}
      {step === 4 && (
        <Card>
          <CardHeader>
            <CardTitle>Шаг 4 — Запуск генерации</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2 rounded-lg border bg-muted/30 p-4 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Пресет</span>
                <span className="font-medium">
                  {selectedPreset?.name ?? selectedPresetId}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">
                  Строк для генерации
                </span>
                <span className="font-medium">
                  {rowsCount ?? "Проверьте JSON на шаге 2"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Режим</span>
                <span className="font-medium">
                  {dryRun ? "Dry-run (проверка)" : "Реальный запуск"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">
                  Ключ идемпотентности
                </span>
                <span className="font-mono text-xs">{idempotencyKey}</span>
              </div>
            </div>
            <ErrorState
              error={runError ?? undefined}
              onRetry={() => void runPack()}
            />
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(3)}>
                Назад
              </Button>
              <Button
                disabled={
                  running ||
                  rowsCount === null ||
                  !idempotencyKey.trim() ||
                  !selectedPresetId
                }
                onClick={() => void runPack()}
              >
                {running
                  ? "Запуск…"
                  : dryRun
                    ? "Запустить Dry-run"
                    : "Запустить генерацию"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 5: Result */}
      {step === 5 && (
        <Card>
          <CardHeader>
            <CardTitle>Готово</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3 text-green-600">
              <CheckCircle className="h-6 w-6" />
              <span className="font-medium">
                {dryRun
                  ? "Dry-run запущен."
                  : "Пакет поставлен в очередь генерации."}
              </span>
            </div>
            {packRunId && (
              <p className="text-sm text-muted-foreground">
                ID запуска: <span className="font-mono">{packRunId}</span>
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {packRunId && (
                <Button onClick={() => navigate(`/pack-runs/${packRunId}`)}>
                  Открыть детали запуска
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() => navigate("/pipelines/runs")}
              >
                История запусков
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  const nextIdempotencyKey = `wizard-${Date.now()}`;
                  const nextStep = presetIdParam ? 2 : 1;
                  setDraftOrigin({
                    step: nextStep,
                    selectedPresetId: presetIdParam,
                    idempotencyKey: nextIdempotencyKey,
                    dryRun: false,
                  });
                  setStep(presetIdParam ? 2 : 1);
                  setSelectedPresetId(presetIdParam);
                  setRowsJson(DEFAULT_ROWS_JSON);
                  rowsJsonRef.current = DEFAULT_ROWS_JSON;
                  setRowsEditorKey((current) => current + 1);
                  setRowsDirty(false);
                  setRowsCount(null);
                  setRowsError(null);
                  setPackRunId(null);
                  setRunError(null);
                  setDryRun(false);
                  setInitialIdempotencyKey(nextIdempotencyKey);
                  setIdempotencyKey(nextIdempotencyKey);
                }}
              >
                Запустить ещё
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default GeneratePackWizardPage;
