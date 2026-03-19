import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import {
  generateDocument,
  generateDocumentsBatch,
  getDocumentBatch,
  getGenerationTaskStatus,
  getReplaceReport,
  replaceDryRun,
  type DocumentBatchItem
} from "@/api/documents";
import { fetchFileDownloadLink } from "@/api/files";
import { getPipelineRun } from "@/api/pipelines";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ReplaceDiffViewer } from "@/components/wizard/ReplaceDiffViewer";
import { WizardJobTimeline } from "@/components/wizard/WizardJobTimeline";
import { WizardStepper } from "@/components/wizard/WizardStepper";
import { useTenantStore } from "@/stores/tenant";
import { useDocumentsWizardStore } from "@/stores/documentsWizard";

const steps = [
  { id: 1, title: "Пресет", description: "Выбор проекта или ручной режим" },
  { id: 2, title: "Файл", description: "Загрузка CSV/XLSX" },
  { id: 3, title: "Маппинг", description: "Колонки → поля" },
  { id: 4, title: "Шаблон", description: "Template code + version" },
  { id: 5, title: "Колонтитулы", description: "Параметры макета" },
  { id: 6, title: "Replace", description: "Dry-run и diff" },
  { id: 7, title: "Запуск", description: "Batch/queue/idempotency" },
  { id: 8, title: "Контроль", description: "Предпросмотр и ошибки" },
  { id: 9, title: "Экспорт", description: "ZIP/PDF" },
  { id: 10, title: "Архив", description: "Архив + ЭДО (MVP)" }
] as const;

const parseCsvColumns = async (file: File) => {
  const text = await file.text();
  const [header] = text.split(/\r?\n/);
  return header
    .split(/[,;]/)
    .map((item) => item.trim())
    .filter(Boolean);
};

const buildBatchErrors = (items: DocumentBatchItem[]) =>
  items
    .filter((item) => item.status === "failed")
    .map((item) => `Строка ${item.row_index}: ${item.error ?? "unknown_error"}`)
    .join("\n");

const getArchiveStatusSummary = ({
  batchStatus,
  pipelineStatus
}: {
  batchStatus?: string | null;
  pipelineStatus?: string | null;
}) => {
  if (pipelineStatus === "done" || batchStatus === "completed") {
    return {
      tone: "text-green-700",
      title: "Архив готов к публикации",
      description: "Артефакты сформированы, можно открыть архив, проверить документы и продолжить согласование/отправку."
    };
  }
  if (pipelineStatus === "failed" || pipelineStatus === "error" || batchStatus === "failed") {
    return {
      tone: "text-destructive",
      title: "Есть ошибки перед архивированием",
      description: "Проверьте timeline pipeline или построчные ошибки batch перед передачей документов дальше."
    };
  }
  return {
    tone: "text-muted-foreground",
    title: "Архив ожидает завершения фоновых задач",
    description: "Следите за статусом pipeline и batch: после завершения отсюда можно перейти в архив и на экран согласований без ручной перезагрузки."
  };
};

const DocumentsWizardPage = () => {
  const tenant = useTenantStore((s) => s.tenant);
  const [searchParams, setSearchParams] = useSearchParams();

  const {
    step,
    preset,
    sourceColumns,
    mapping,
    templateCode,
    templateVersion,
    companyId,
    headerPreset,
    replaceDryRun: replaceDryRunResult,
    batch,
    taskId,
    pipelineRun,
    idempotencyKey,
    rowStatusFilter,
    setPartial
  } = useDocumentsWizardStore();

  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [replaceMapFile, setReplaceMapFile] = useState<File | null>(null);
  const [docxFile, setDocxFile] = useState<File | null>(null);
  const [batchErrors, setBatchErrors] = useState("");

  useEffect(() => {
    const stepFromQuery = Number(searchParams.get("step") ?? step);
    if (Number.isFinite(stepFromQuery) && stepFromQuery >= 1 && stepFromQuery <= 10 && stepFromQuery !== step) {
      setPartial({ step: stepFromQuery });
    }
  }, [searchParams, setPartial, step]);

  useEffect(() => {
    const current = Number(searchParams.get("step") ?? 0);
    if (current !== step) {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("step", String(step));
        return next;
      });
    }
  }, [searchParams, setSearchParams, step]);

  useEffect(() => {
    if (!taskId || !tenant) return;
    if (pipelineRun && !["queued", "running"].includes(pipelineRun.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const run = await getPipelineRun(taskId);
        setPartial({ pipelineRun: run });
      } catch {
        toast.error("Не удалось обновить timeline job.");
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [pipelineRun, setPartial, taskId, tenant]);

  useEffect(() => {
    if (!batch?.id || !tenant) return;
    if (!["queued", "running"].includes(batch.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const updated = await getDocumentBatch(batch.id);
        setPartial({ batch: updated });
      } catch {
        toast.error("Не удалось обновить batch статус.");
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [batch?.id, batch?.status, setPartial, tenant]);

  const filteredBatchItems = useMemo(() => {
    if (!batch) return [];
    if (rowStatusFilter === "all") return batch.items;
    return batch.items.filter((item) => item.status === rowStatusFilter);
  }, [batch, rowStatusFilter]);
  const archiveStatus = getArchiveStatusSummary({
    batchStatus: batch?.status,
    pipelineStatus: pipelineRun?.status
  });

  const canCallApi = Boolean(tenant);

  const nextStep = () => setPartial({ step: Math.min(step + 1, 10) });
  const prevStep = () => setPartial({ step: Math.max(step - 1, 1) });

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Документы" }, { label: "Мастер пакета" }]} />
      {!tenant ? (
        <Card>
          <CardContent className="pt-6 text-sm text-destructive">Выберите tenant перед запуском мастера. Без X-Tenant запросы заблокированы.</CardContent>
        </Card>
      ) : null}
      <WizardStepper steps={steps.map((item) => ({ ...item }))} currentStep={step} onStepClick={(s) => setPartial({ step: s })} />

      <Card>
        <CardHeader>
          <CardTitle>Шаг {step}: {steps[step - 1].title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {step === 1 ? (
            <div className="space-y-2">
              <Label>Preset / project</Label>
              <Input value={preset} onChange={(e) => setPartial({ preset: e.target.value })} placeholder="manual / outbound_mvp / ..." />
            </div>
          ) : null}

          {step === 2 ? (
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
          ) : null}

          {step === 3 ? (
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
          ) : null}

          {step === 4 ? (
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
          ) : null}

          {step === 5 ? (
            <div className="space-y-2">
              <Label>Preset колонтитулов</Label>
              <Input value={headerPreset} onChange={(e) => setPartial({ headerPreset: e.target.value })} placeholder="default / company_brand" />
            </div>
          ) : null}

          {step === 6 ? (
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
                  if (!docxFile || !replaceMapFile) return;
                  const result = await replaceDryRun({
                    docxFile,
                    replaceMapFile,
                    idempotencyKey
                  });
                  setPartial({ replaceDryRun: result });
                  const fullReport = await getReplaceReport(result.report_id, { limit: 100 });
                  setPartial({ replaceDryRun: { ...result, preview_samples: fullReport.rows } });
                }}
              >
                Выполнить dry-run
              </Button>
              {replaceDryRunResult ? <ReplaceDiffViewer items={replaceDryRunResult.preview_samples} summary={replaceDryRunResult.summary} /> : null}
            </div>
          ) : null}

          {step === 7 ? (
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
                    if (!sourceFile) return;
                    const response = await generateDocumentsBatch({
                      file: sourceFile,
                      templateCode,
                      templateVersion,
                      companyId
                    });
                    setPartial({ batch: response });
                    toast.success("Batch запущен");
                  }}
                >
                  Запустить batch по строкам
                </Button>
                <Button
                  variant="outline"
                  disabled={!canCallApi || !templateCode || !companyId}
                  onClick={async () => {
                    const payload = {
                      template_code: templateCode,
                      template_version: templateVersion,
                      company_id: companyId,
                      data: { preset, mapping, headerPreset }
                    };
                    const task = await generateDocument(payload, idempotencyKey);
                    const status = await getGenerationTaskStatus(task.task_id);
                    setPartial({ taskId: task.task_id });
                    const run = await getPipelineRun(task.task_id);
                    setPartial({ pipelineRun: run });
                    if (status.status === "failed" || status.status === "error") {
                      toast.error(status.error ?? "Pipeline завершился с ошибкой");
                    }
                  }}
                >
                  Запустить single pipeline
                </Button>
              </div>
              {pipelineRun ? <WizardJobTimeline steps={pipelineRun.step_runs} /> : null}
            </div>
          ) : null}

          {step === 8 ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Label>Фильтр строк:</Label>
                <select
                  className="h-9 rounded border bg-background px-2 text-sm"
                  value={rowStatusFilter}
                  onChange={(e) => setPartial({ rowStatusFilter: e.target.value as "all" | "success" | "failed" })}
                >
                  <option value="all">all</option>
                  <option value="success">success</option>
                  <option value="failed">failed</option>
                </select>
              </div>
              {batch ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>#</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead>error</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredBatchItems.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>{item.row_index}</TableCell>
                        <TableCell>{item.status}</TableCell>
                        <TableCell className="text-xs text-destructive">{item.error}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground">Batch еще не запущен.</p>
              )}
              <Textarea value={batchErrors} onChange={(e) => setBatchErrors(e.target.value)} placeholder="Страница ошибок батча" />
              <Button variant="outline" disabled={!batch} onClick={() => setBatchErrors(buildBatchErrors(batch?.items ?? []))}>
                Сформировать ошибки построчно
              </Button>
            </div>
          ) : null}

          {step === 9 ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Экспорт доступен после успешного pipeline. Ссылки берутся из artifacts и /v1/files/&lt;id&gt;/download.</p>
              <Button
                variant="outline"
                disabled={!pipelineRun?.artifacts}
                onClick={async () => {
                  const fileId = String((pipelineRun?.artifacts?.all as Array<{ file_id?: string }> | undefined)?.[0]?.file_id ?? "");
                  if (!fileId) {
                    toast.error("Файл артефакта не найден.");
                    return;
                  }
                  const link = await fetchFileDownloadLink(fileId);
                  window.open(link.url, "_blank", "noopener,noreferrer");
                }}
              >
                Скачать первый артефакт (ZIP/PDF)
              </Button>
            </div>
          ) : null}

          {step === 10 ? (
            <div className="space-y-2 text-sm">
              <div className={`rounded-lg border bg-muted/30 p-4 ${archiveStatus.tone}`}>
                <p className="font-medium">{archiveStatus.title}</p>
                <p className="mt-1 text-sm">{archiveStatus.description}</p>
                <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                  <div>
                    <span className="text-muted-foreground">Pipeline:</span>{" "}
                    <span className="font-medium">{pipelineRun?.status ?? "не запускался"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Batch:</span>{" "}
                    <span className="font-medium">{batch?.status ?? "не запускался"}</span>
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
          ) : null}

          <div className="flex justify-between border-t pt-3">
            <Button variant="outline" onClick={prevStep} disabled={step === 1}>Назад</Button>
            <Button onClick={nextStep} disabled={step === 10}>Далее</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default DocumentsWizardPage;
