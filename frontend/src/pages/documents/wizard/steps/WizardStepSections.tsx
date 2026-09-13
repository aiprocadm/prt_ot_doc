import type { ChangeEvent } from "react";
import { memo } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
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
import { WizardJobTimeline } from "@/components/wizard/WizardJobTimeline";

import { previewSectionCards } from "../constants";
import { buildBatchErrors } from "../utils";
import type { WizardStepContentProps } from "../WizardStepContent.types";

type SharedProps = Pick<
  WizardStepContentProps,
  | "setPartial"
  | "canCallApi"
  | "preset"
  | "sourceColumns"
  | "mapping"
  | "mappingValidation"
  | "qualityReport"
  | "templateCode"
  | "templateVersion"
  | "companyId"
  | "siteId"
  | "headerPreset"
  | "companies"
  | "sites"
  | "layoutPresets"
  | "brandingPreview"
  | "brandingPreviewHistory"
  | "brandingProfileScope"
  | "idempotencyKey"
  | "replaceDryRunResult"
  | "batch"
  | "pipelineRun"
  | "rowStatusFilter"
  | "filteredBatchItems"
  | "batchErrors"
  | "setBatchErrors"
  | "sourceFile"
  | "replaceMapFile"
  | "docxFile"
  | "setDocxFile"
  | "archiveStatus"
>;

export const PresetStep = ({
  preset,
  setPartial,
}: Pick<SharedProps, "preset" | "setPartial">) => (
  <div className="space-y-2">
    <Label>Пресет / проект</Label>
    <Input
      value={preset}
      onChange={(e) => setPartial({ preset: e.target.value })}
      placeholder="manual, outbound_mvp, …"
    />
  </div>
);

export const SourceStep = ({
  sourceColumns,
  onSourceChange,
}: {
  sourceColumns: string[];
  onSourceChange: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
}) => (
  <div className="space-y-2">
    <Label>CSV/XLSX/DOC/DOCX файл (до 10MB)</Label>
    <Input
      type="file"
      accept=".csv,.xlsx,.doc,.docx"
      className="file:mr-3 file:rounded-md file:border file:border-input file:bg-muted file:px-3 file:py-1 file:text-sm hover:file:bg-muted/80"
      onChange={(event) => void onSourceChange(event)}
    />
    <div className="text-xs text-muted-foreground">
      Колонки: {sourceColumns.join(", ") || "не определены"}
    </div>
  </div>
);

export const MappingStep = ({
  sourceColumns,
  mapping,
  mappingValidation,
  setPartial,
  onValidate,
}: Pick<
  SharedProps,
  "sourceColumns" | "mapping" | "mappingValidation" | "setPartial"
> & { onValidate: () => Promise<void> }) => (
  <div className="space-y-3">
    <Label>Маппинг полей</Label>
    {sourceColumns.length === 0 ? (
      <p className="text-sm text-muted-foreground">
        Сначала загрузите CSV, чтобы увидеть колонки.
      </p>
    ) : null}
    <div className="grid gap-2 md:grid-cols-2">
      {sourceColumns.map((column) => (
        <div key={column} className="space-y-1">
          <Label>{column}</Label>
          <Input
            placeholder="целевое_поле"
            value={mapping[column] ?? ""}
            onChange={(event) =>
              setPartial({
                mapping: {
                  ...mapping,
                  [column]: event.target.value,
                },
              })
            }
          />
        </div>
      ))}
    </div>
    <Button
      variant="outline"
      onClick={() => void onValidate()}
      disabled={sourceColumns.length === 0}
    >
      Проверить сопоставление
    </Button>
    {mappingValidation ? (
      <div className="rounded-md border bg-muted/20 p-3 text-xs">
        <div>ok: {String(mappingValidation.ok)}</div>
        <div>
          missing required:{" "}
          {mappingValidation.missing_required_fields.join(", ") || "none"}
        </div>
        <div>
          unmapped source:{" "}
          {mappingValidation.unmapped_source_fields.join(", ") || "none"}
        </div>
      </div>
    ) : null}
  </div>
);

export const TemplateStep = ({
  templateCode,
  templateVersion,
  setPartial,
}: Pick<SharedProps, "templateCode" | "templateVersion" | "setPartial">) => (
  <div className="grid gap-3 md:grid-cols-2">
    <div className="space-y-2">
      <Label>Код шаблона</Label>
      <Input
        value={templateCode}
        onChange={(e) => setPartial({ templateCode: e.target.value })}
        placeholder="outbound_cover"
      />
    </div>
    <div className="space-y-2">
      <Label>Версия</Label>
      <Input
        type="number"
        min={1}
        value={templateVersion}
        onChange={(e) =>
          setPartial({ templateVersion: Number(e.target.value) })
        }
      />
    </div>
  </div>
);

export const BrandingStep = ({
  canCallApi,
  companyId,
  siteId,
  headerPreset,
  companies,
  sites,
  layoutPresets,
  brandingPreview,
  brandingPreviewHistory,
  brandingProfileScope,
  setPartial,
  onBuildPreview,
}: Pick<
  SharedProps,
  | "canCallApi"
  | "companyId"
  | "siteId"
  | "headerPreset"
  | "companies"
  | "sites"
  | "layoutPresets"
  | "brandingPreview"
  | "brandingPreviewHistory"
  | "brandingProfileScope"
  | "setPartial"
> & { onBuildPreview: () => Promise<void> }) => (
  <div className="space-y-4">
    <div className="grid gap-3 md:grid-cols-3">
      <div className="space-y-2">
        <Label>Организация</Label>
        <select
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={companyId}
          onChange={(e) =>
            setPartial({ companyId: e.target.value, siteId: "" })
          }
        >
          <option value="">Выберите организацию</option>
          {companies.map((company) => (
            <option key={company.id} value={company.id}>
              {company.name}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <Label>Филиал / объект</Label>
        <select
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={siteId}
          onChange={(e) => setPartial({ siteId: e.target.value })}
        >
          <option value="">Уровень организации</option>
          {sites.map((site) => (
            <option key={site.id} value={site.id}>
              {site.name}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <Label>Preset колонтитулов</Label>
        <select
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={headerPreset}
          onChange={(e) => setPartial({ headerPreset: e.target.value })}
        >
          <option value="">Авто по brand profile</option>
          {layoutPresets.map((presetOption) => (
            <option key={presetOption.id} value={presetOption.code}>
              {presetOption.code} — {presetOption.name}
            </option>
          ))}
        </select>
      </div>
    </div>
    <div className="flex flex-wrap gap-2">
      <Button
        variant="outline"
        disabled={!canCallApi || !companyId}
        onClick={() => void onBuildPreview()}
      >
        Собрать превью с брендингом
      </Button>
      <Button asChild variant="ghost">
        <Link to="/documents/branding">Открыть настройки брендинга</Link>
      </Button>
    </div>
    <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
      <div className="rounded-lg border bg-muted/20 p-4 text-sm">
        <div className="font-medium">Превью колонтитулов</div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {previewSectionCards.map((section) => (
            <div
              key={section.key}
              className="rounded-md border bg-background p-3"
            >
              <div className="text-xs text-muted-foreground">
                {section.label}
              </div>
              <div className="mt-2 whitespace-pre-wrap">
                {brandingPreview?.sections[section.key] ?? "—"}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="space-y-3 rounded-lg border bg-muted/20 p-4 text-sm">
        <div>
          <div className="font-medium">Снимок воспроизводимости</div>
          <pre className="mt-2 overflow-x-auto rounded-md border bg-background p-3 text-xs">
            {JSON.stringify(
              brandingPreview?.profile.reproducibility ?? {},
              null,
              2,
            )}
          </pre>
        </div>
        <div className="rounded-md border bg-background p-3">
          <div className="font-medium">Разрешение / источник пресета</div>
          <div className="mt-2">
            preset={(brandingPreview?.preset_code ?? headerPreset) || "auto"}
          </div>
          <div>
            scope={brandingPreview?.profile.scope ?? brandingProfileScope}
          </div>
          <div>
            source=
            {brandingPreview?.profile.resolution?.effective_preset_source ??
              "—"}
          </div>
          <div>
            scope_chain=
            {(brandingPreview?.profile.resolution?.scope_chain ?? []).join(
              " > ",
            ) || "—"}
          </div>
        </div>
        <div>
          <div className="font-medium">Недавняя история превью</div>
          <div className="mt-2 space-y-2">
            {brandingPreviewHistory.length === 0 ? (
              <div className="text-muted-foreground">
                История появится после сборки превью.
              </div>
            ) : (
              brandingPreviewHistory.map((item, index) => (
                <div
                  key={`${String(item.profile.reproducibility.generated_at ?? index)}`}
                  className="rounded-md border bg-background p-2 text-xs"
                >
                  <div>
                    {String(
                      item.profile.reproducibility.generated_at ?? "unknown",
                    )}
                  </div>
                  <div>preset={item.preset_code ?? "—"}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  </div>
);

/**
 * Срез-154: шаг пробной замены больше не предлагает действие, которого нет.
 *
 * Форма загружала DOCX и CSV-карту и звала `POST /replace/dry-run` — контракт,
 * снятый вместе со старым движком замены: кнопка «Выполнить dry-run» всегда
 * кончалась 404 и тостом «Не удалось выполнить dry-run replace». Сегодня
 * сервер заменяет в УЖЕ СОЗДАННОМ документе платформы по СОХРАНЁННОЙ карте
 * замен, а произвольный файл с диска в этот контракт не ложится: у него нет
 * версии документа, и витрины карт замен в продукте нет вовсе.
 *
 * Поэтому шаг объясняет положение словами и не обещает работу. Нумерация
 * шагов сохранена намеренно: у мастера сохраняется текущий шаг, и сдвиг
 * увёл бы человека не на тот экран.
 */
export const ReplaceStep = memo(() => (
  <div className="space-y-3">
    <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">
        Пробная замена пока недоступна
      </p>
      <p className="mt-1">
        Раньше здесь можно было принести свой DOCX и CSV-карту замен. Платформа
        перешла на замену в уже созданных документах по сохранённой карте, а
        экрана карт замен пока нет — поэтому шаг ничего не просит и ничего не
        обещает.
      </p>
      <p className="mt-1">
        Документы собираются дальше: перейдите к шагу «Запуск».
      </p>
    </div>
  </div>
));

ReplaceStep.displayName = "ReplaceStep";

export const RunStep = ({
  canCallApi,
  sourceFile,
  templateCode,
  companyId,
  idempotencyKey,
  pipelineRun,
  qualityReport,
  setPartial,
  onRunBatch,
  onRunSinglePipeline,
}: Pick<
  SharedProps,
  | "canCallApi"
  | "sourceFile"
  | "templateCode"
  | "companyId"
  | "idempotencyKey"
  | "pipelineRun"
  | "qualityReport"
  | "setPartial"
> & {
  onRunBatch: () => Promise<void>;
  onRunSinglePipeline: () => Promise<void>;
}) => (
  <div className="space-y-3">
    <div className="grid gap-3 md:grid-cols-2">
      <div className="space-y-2">
        <Label>ID организации</Label>
        <Input
          value={companyId}
          onChange={(e) => setPartial({ companyId: e.target.value })}
          placeholder="UUID компании"
        />
      </div>
      <div className="space-y-2">
        <Label>Ключ идемпотентности</Label>
        <Input
          value={idempotencyKey}
          onChange={(e) => setPartial({ idempotencyKey: e.target.value })}
        />
      </div>
    </div>
    <div className="flex flex-wrap gap-2">
      <Button
        disabled={!canCallApi || !sourceFile || !templateCode || !companyId}
        onClick={() => void onRunBatch()}
      >
        Запустить batch по строкам
      </Button>
      <Button
        variant="outline"
        disabled={!canCallApi || !templateCode || !companyId}
        onClick={() => void onRunSinglePipeline()}
      >
        Запустить одиночный пайплайн
      </Button>
    </div>
    {pipelineRun ? <WizardJobTimeline steps={pipelineRun.step_runs} /> : null}
    {qualityReport ? (
      <div className="rounded-md border bg-muted/20 p-3 text-xs">
        <div>quality status: {qualityReport.status}</div>
        <div>critical: {qualityReport.summary.critical ?? 0}</div>
        <div>warning: {qualityReport.summary.warning ?? 0}</div>
      </div>
    ) : null}
  </div>
);

export const BatchResultStep = memo(
  ({
    rowStatusFilter,
    setPartial,
    batch,
    filteredBatchItems,
    batchErrors,
    setBatchErrors,
  }: Pick<
    SharedProps,
    | "rowStatusFilter"
    | "setPartial"
    | "batch"
    | "filteredBatchItems"
    | "batchErrors"
    | "setBatchErrors"
  >) => (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Label>Фильтр строк:</Label>
        <select
          className="h-9 rounded border bg-background px-2 text-sm"
          value={rowStatusFilter}
          onChange={(e) =>
            setPartial({
              rowStatusFilter: e.target.value as "all" | "success" | "failed",
            })
          }
        >
          <option value="all">все</option>
          <option value="success">успех</option>
          <option value="failed">ошибка</option>
        </select>
      </div>
      {batch ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>#</TableHead>
              <TableHead>статус</TableHead>
              <TableHead>ошибка</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredBatchItems.map((item) => (
              <TableRow key={item.id}>
                <TableCell>{item.row_index}</TableCell>
                <TableCell>{item.status}</TableCell>
                <TableCell className="text-xs text-destructive">
                  {item.error}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <p className="text-sm text-muted-foreground">Batch еще не запущен.</p>
      )}
      <Textarea
        value={batchErrors}
        onChange={(e) => setBatchErrors(e.target.value)}
        placeholder="Страница ошибок батча"
      />
      <Button
        variant="outline"
        disabled={!batch}
        onClick={() => setBatchErrors(buildBatchErrors(batch?.items ?? []))}
      >
        Сформировать ошибки построчно
      </Button>
    </div>
  ),
);

BatchResultStep.displayName = "BatchResultStep";

export const ExportStep = ({
  pipelineRun,
  onOpenArtifact,
}: Pick<SharedProps, "pipelineRun"> & {
  onOpenArtifact: () => Promise<void>;
}) => (
  <div className="space-y-3">
    <p className="text-sm text-muted-foreground">
      Экспорт доступен после успешного пайплайна. Ссылки берутся из артефактов и
      эндпоинтов `/api/v1/files/...`.
    </p>
    <Button
      variant="outline"
      disabled={!pipelineRun?.artifacts}
      onClick={() => void onOpenArtifact()}
    >
      Скачать первый артефакт (ZIP/PDF)
    </Button>
  </div>
);

export const ArchiveStep = ({
  archiveStatus,
  pipelineRun,
  batch,
}: Pick<SharedProps, "archiveStatus" | "pipelineRun" | "batch">) => (
  <div className="space-y-2 text-sm">
    <div className={`rounded-lg border bg-muted/30 p-4 ${archiveStatus.tone}`}>
      <p className="font-medium">{archiveStatus.title}</p>
      <p className="mt-1 text-sm">{archiveStatus.description}</p>
      <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
        <div>
          <span className="text-muted-foreground">Пайплайн:</span>{" "}
          <span className="font-medium">
            {pipelineRun?.status ?? "не запускался"}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">Пакет:</span>{" "}
          <span className="font-medium">
            {batch?.status ?? "не запускался"}
          </span>
        </div>
      </div>
    </div>
    <div className="flex gap-2">
      <Button asChild>
        <Link to="/archive">Перейти в архив</Link>
      </Button>
      <Button asChild variant="outline">
        <Link to="/approvals">Открыть согласование / подпись</Link>
      </Button>
    </div>
  </div>
);
