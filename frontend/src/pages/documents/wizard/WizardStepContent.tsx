import { Link } from "react-router-dom";
import { toast } from "sonner";

import {
  generateDocument,
  generateDocumentsBatch,
  getGenerationTaskStatus,
  getReplaceReport,
  replaceDryRun,
  type DocumentBatchRun,
  type DocumentBatchItem,
  type ReplaceDryRunResponse
} from "@/api/documents";
import { previewBranding, type BrandingPreviewDto, type LayoutPresetDto, type SiteDto } from "@/api/branding";
import { fetchFileDownloadLink } from "@/api/files";
import { getPipelineRun, type PipelineRun } from "@/api/pipelines";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ReplaceDiffViewer } from "@/components/wizard/ReplaceDiffViewer";
import { WizardJobTimeline } from "@/components/wizard/WizardJobTimeline";

import { previewSectionCards } from "./constants";
import { type DocumentsWizardState } from "@/stores/documentsWizard";
import { buildBatchErrors, parseCsvColumns } from "./utils";

type RowStatusFilter = "all" | "success" | "failed";

type Props = {
  step: number;
  canCallApi: boolean;
  sourceColumns: string[];
  mapping: Record<string, string>;
  preset: string;
  templateCode: string;
  templateVersion: number;
  companyId: string;
  siteId: string;
  headerPreset: string;
  idempotencyKey: string;
  rowStatusFilter: RowStatusFilter;
  filteredBatchItems: DocumentBatchItem[];
  replaceDryRunResult: ReplaceDryRunResponse | null;
  batch: DocumentBatchRun | null;
  pipelineRun: PipelineRun | null;
  brandingPreview: BrandingPreviewDto | null;
  brandingPreviewHistory: BrandingPreviewDto[];
  brandingProfileScope: string;
  companies: Array<{ id: string; name: string }>;
  sites: SiteDto[];
  layoutPresets: LayoutPresetDto[];
  sourceFile: File | null;
  replaceMapFile: File | null;
  docxFile: File | null;
  batchErrors: string;
  setSourceFile: (value: File | null) => void;
  setReplaceMapFile: (value: File | null) => void;
  setDocxFile: (value: File | null) => void;
  setBatchErrors: (value: string) => void;
  pushBrandingPreview: DocumentsWizardState["pushBrandingPreview"];
  setPartial: DocumentsWizardState["setPartial"];
  archiveStatus: { tone: string; title: string; description: string };
};

export const WizardStepContent = ({
  step,
  canCallApi,
  sourceColumns,
  mapping,
  preset,
  templateCode,
  templateVersion,
  companyId,
  siteId,
  headerPreset,
  idempotencyKey,
  rowStatusFilter,
  filteredBatchItems,
  replaceDryRunResult,
  batch,
  pipelineRun,
  brandingPreview,
  brandingPreviewHistory,
  brandingProfileScope,
  companies,
  sites,
  layoutPresets,
  sourceFile,
  replaceMapFile,
  docxFile,
  batchErrors,
  setSourceFile,
  setReplaceMapFile,
  setDocxFile,
  setBatchErrors,
  pushBrandingPreview,
  setPartial,
  archiveStatus
}: Props) => {
  if (step === 1) {
    return (
      <div className="space-y-2">
        <Label>Preset / project</Label>
        <Input value={preset} onChange={(e) => setPartial({ preset: e.target.value })} placeholder="manual / outbound_mvp / ..." />
      </div>
    );
  }

  if (step === 2) {
    return (
      <div className="space-y-2">
        <Label>CSV/XLSX файл (до 10MB)</Label>
        <Input
          type="file"
          accept=".csv,.xlsx"
          onChange={async (event) => {
            const file = event.target.files?.[0] ?? null;
            if (!file) return;
            if (file.size > 10 * 1024 * 1024) {
              toast.error("Файл слишком большой (лимит 10MB)");
              return;
            }
            setSourceFile(file);
            setPartial({ sourceFileName: file.name });
            if (file.name.endsWith(".csv")) {
              const columns = await parseCsvColumns(file);
              setPartial({ sourceColumns: columns });
            }
          }}
        />
        <div className="text-xs text-muted-foreground">Колонки: {sourceColumns.join(", ") || "не определены"}</div>
      </div>
    );
  }

  if (step === 3) {
    return (
      <div className="space-y-3">
        <Label>Маппинг полей</Label>
        {sourceColumns.length === 0 ? <p className="text-sm text-muted-foreground">Сначала загрузите CSV, чтобы увидеть колонки.</p> : null}
        <div className="grid gap-2 md:grid-cols-2">
          {sourceColumns.map((column) => (
            <div key={column} className="space-y-1">
              <Label>{column}</Label>
              <Input
                placeholder="target_field"
                value={mapping[column] ?? ""}
                onChange={(event) =>
                  setPartial({
                    mapping: {
                      ...mapping,
                      [column]: event.target.value
                    }
                  })
                }
              />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (step === 4) {
    return (
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <Label>Template code</Label>
          <Input value={templateCode} onChange={(e) => setPartial({ templateCode: e.target.value })} placeholder="outbound_cover" />
        </div>
        <div className="space-y-2">
          <Label>Version</Label>
          <Input type="number" min={1} value={templateVersion} onChange={(e) => setPartial({ templateVersion: Number(e.target.value) })} />
        </div>
      </div>
    );
  }

  if (step === 5) {
    return (
      <div className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-2">
            <Label>Организация</Label>
            <select className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={companyId} onChange={(e) => setPartial({ companyId: e.target.value, siteId: "" })}>
              <option value="">Выберите организацию</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>{company.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>Филиал / объект</Label>
            <select className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={siteId} onChange={(e) => setPartial({ siteId: e.target.value })}>
              <option value="">Уровень организации</option>
              {sites.map((site) => (
                <option key={site.id} value={site.id}>{site.name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label>Preset колонтитулов</Label>
            <select className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={headerPreset} onChange={(e) => setPartial({ headerPreset: e.target.value })}>
              <option value="">Авто по brand profile</option>
              {layoutPresets.map((presetOption) => (
                <option key={presetOption.id} value={presetOption.code}>{presetOption.code} — {presetOption.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={!canCallApi || !companyId}
            onClick={async () => {
              try {
                if (!companyId) return;
                const preview = await previewBranding({
                  company_id: companyId,
                  site_id: siteId || undefined,
                  preset_code: headerPreset || undefined,
                  document_title: templateCode || "Branded document",
                  document_number: `preview-${templateVersion}`,
                  watermark_override: { enabled: true, text: "PREVIEW" }
                });
                pushBrandingPreview(preview);
                setPartial({
                  companyId: (preview.wizard_defaults.company_id as string | undefined) ?? companyId,
                  siteId: (preview.wizard_defaults.site_id as string | undefined) ?? siteId,
                  headerPreset: (preview.wizard_defaults.preset_code as string | undefined) ?? headerPreset,
                });
              } catch (error) {
                toast.error(error instanceof Error ? error.message : "Не удалось собрать branded preview");
              }
            }}
          >
            Собрать branded preview
          </Button>
          <Button asChild variant="ghost"><Link to="/documents/branding">Открыть branding settings</Link></Button>
        </div>
        <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-lg border bg-muted/20 p-4 text-sm">
            <div className="font-medium">Preview header/footer</div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {previewSectionCards.map((section) => (
                <div key={section.key} className="rounded-md border bg-background p-3">
                  <div className="text-xs text-muted-foreground">{section.label}</div>
                  <div className="mt-2 whitespace-pre-wrap">{brandingPreview?.sections[section.key] ?? "—"}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-3 rounded-lg border bg-muted/20 p-4 text-sm">
            <div>
              <div className="font-medium">Reproducibility snapshot</div>
              <pre className="mt-2 overflow-x-auto rounded-md border bg-background p-3 text-xs">{JSON.stringify(brandingPreview?.profile.reproducibility ?? {}, null, 2)}</pre>
            </div>
            <div className="rounded-md border bg-background p-3">
              <div className="font-medium">Resolution / preset source</div>
              <div className="mt-2">preset={(brandingPreview?.preset_code ?? headerPreset) || "auto"}</div>
              <div>scope={brandingPreview?.profile.scope ?? brandingProfileScope}</div>
            </div>
            <div>
              <div className="font-medium">Recent preview history</div>
              <div className="mt-2 space-y-2">
                {brandingPreviewHistory.length === 0 ? (
                  <div className="text-muted-foreground">История появится после preview.</div>
                ) : (
                  brandingPreviewHistory.map((item, index) => (
                    <div key={`${String(item.profile.reproducibility.generated_at ?? index)}`} className="rounded-md border bg-background p-2 text-xs">
                      <div>{String(item.profile.reproducibility.generated_at ?? "unknown")}</div>
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
  }

  if (step === 6) {
    return (
      <div className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label>DOCX для dry-run replace</Label>
            <Input type="file" accept=".docx" onChange={(event) => setDocxFile(event.target.files?.[0] ?? null)} />
          </div>
          <div className="space-y-2">
            <Label>CSV карта замен (from,to)</Label>
            <Input type="file" accept=".csv" onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              setReplaceMapFile(file);
              setPartial({ replaceMapFileName: file?.name ?? "" });
            }} />
          </div>
        </div>
        <Button
          disabled={!canCallApi || !docxFile || !replaceMapFile}
          onClick={async () => {
            try {
              if (!docxFile || !replaceMapFile) return;
              const result = await replaceDryRun({ docxFile, replaceMapFile, idempotencyKey });
              setPartial({ replaceDryRun: result });
              const fullReport = await getReplaceReport(result.report_id, { limit: 100 });
              setPartial({ replaceDryRun: { ...result, preview_samples: fullReport.rows } });
            } catch (error) {
              toast.error(error instanceof Error ? error.message : "Не удалось выполнить dry-run replace");
            }
          }}
        >
          Выполнить dry-run
        </Button>
        {replaceDryRunResult ? <ReplaceDiffViewer items={replaceDryRunResult.preview_samples} summary={replaceDryRunResult.summary} /> : null}
      </div>
    );
  }

  if (step === 7) {
    return (
      <div className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Company ID</Label>
            <Input value={companyId} onChange={(e) => setPartial({ companyId: e.target.value })} placeholder="UUID компании" />
          </div>
          <div className="space-y-2">
            <Label>Idempotency-Key</Label>
            <Input value={idempotencyKey} onChange={(e) => setPartial({ idempotencyKey: e.target.value })} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={!canCallApi || !sourceFile || !templateCode || !companyId}
            onClick={async () => {
              try {
                if (!sourceFile) return;
                const response = await generateDocumentsBatch({ file: sourceFile, templateCode, templateVersion, companyId });
                setPartial({ batch: response });
                toast.success("Batch запущен");
              } catch (error) {
                toast.error(error instanceof Error ? error.message : "Не удалось запустить batch");
              }
            }}
          >
            Запустить batch по строкам
          </Button>
          <Button
            variant="outline"
            disabled={!canCallApi || !templateCode || !companyId}
            onClick={async () => {
              try {
                const payload = {
                  template_code: templateCode,
                  template_version: templateVersion,
                  company_id: companyId,
                  data: { preset, mapping, headerPreset, siteId: siteId || null, branding_preview: brandingPreview?.apply_headers_payload ?? null, reproducibility: brandingPreview?.profile.reproducibility ?? null }
                };
                const task = await generateDocument(payload, idempotencyKey);
                const status = await getGenerationTaskStatus(task.task_id);
                setPartial({ taskId: task.task_id });
                const run = await getPipelineRun(task.task_id);
                setPartial({ pipelineRun: run });
                if (status.status === "failed" || status.status === "error") {
                  toast.error(status.error ?? "Pipeline завершился с ошибкой");
                }
              } catch (error) {
                toast.error(error instanceof Error ? error.message : "Не удалось запустить single pipeline");
              }
            }}
          >
            Запустить single pipeline
          </Button>
        </div>
        {pipelineRun ? <WizardJobTimeline steps={pipelineRun.step_runs} /> : null}
      </div>
    );
  }

  if (step === 8) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Label>Фильтр строк:</Label>
          <select className="h-9 rounded border bg-background px-2 text-sm" value={rowStatusFilter} onChange={(e) => setPartial({ rowStatusFilter: e.target.value as RowStatusFilter })}>
            <option value="all">all</option>
            <option value="success">success</option>
            <option value="failed">failed</option>
          </select>
        </div>
        {batch ? (
          <Table>
            <TableHeader>
              <TableRow><TableHead>#</TableHead><TableHead>status</TableHead><TableHead>error</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {filteredBatchItems.map((item) => (
                <TableRow key={item.id}><TableCell>{item.row_index}</TableCell><TableCell>{item.status}</TableCell><TableCell className="text-xs text-destructive">{item.error}</TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-sm text-muted-foreground">Batch еще не запущен.</p>
        )}
        <Textarea value={batchErrors} onChange={(e) => setBatchErrors(e.target.value)} placeholder="Страница ошибок батча" />
        <Button variant="outline" disabled={!batch} onClick={() => setBatchErrors(buildBatchErrors(batch?.items ?? []))}>Сформировать ошибки построчно</Button>
      </div>
    );
  }

  if (step === 9) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">Экспорт доступен после успешного pipeline. Ссылки берутся из artifacts и /v1/files/&lt;id&gt;/download.</p>
        <Button
          variant="outline"
          disabled={!pipelineRun?.artifacts}
          onClick={async () => {
            try {
              const fileId = String((pipelineRun?.artifacts?.all as Array<{ file_id?: string }> | undefined)?.[0]?.file_id ?? "");
              if (!fileId) {
                toast.error("Файл артефакта не найден.");
                return;
              }
              const link = await fetchFileDownloadLink(fileId);
              window.open(link.url, "_blank", "noopener,noreferrer");
            } catch (error) {
              toast.error(error instanceof Error ? error.message : "Не удалось скачать артефакт");
            }
          }}
        >
          Скачать первый артефакт (ZIP/PDF)
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-2 text-sm">
      <div className={`rounded-lg border bg-muted/30 p-4 ${archiveStatus.tone}`}>
        <p className="font-medium">{archiveStatus.title}</p>
        <p className="mt-1 text-sm">{archiveStatus.description}</p>
        <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
          <div><span className="text-muted-foreground">Pipeline:</span> <span className="font-medium">{pipelineRun?.status ?? "не запускался"}</span></div>
          <div><span className="text-muted-foreground">Batch:</span> <span className="font-medium">{batch?.status ?? "не запускался"}</span></div>
        </div>
      </div>
      <div className="flex gap-2">
        <Button asChild><Link to="/archive">Перейти в архив</Link></Button>
        <Button asChild variant="outline"><Link to="/approvals">Открыть согласование / подпись</Link></Button>
      </div>
    </div>
  );
};
