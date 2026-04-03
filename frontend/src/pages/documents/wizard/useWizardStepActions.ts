import type { ChangeEvent } from "react";
import { toast } from "sonner";

import { fetchFileDownloadLink } from "@/api/files";
import {
  generateDocument,
  generateDocumentsBatch,
  getGenerationTaskStatus,
  getReplaceReport,
  replaceDryRun,
} from "@/api/documents";
import { previewBranding } from "@/api/branding";
import { getPipelineRun } from "@/api/pipelines";
import { parseCsvColumns } from "./utils";
import type { WizardStepContentProps } from "./WizardStepContent.types";

type ActionDeps = Pick<
  WizardStepContentProps,
  | "setPartial"
  | "setSourceFile"
  | "setReplaceMapFile"
  | "setDocxFile"
  | "setBatchErrors"
  | "pushBrandingPreview"
  | "canCallApi"
  | "companyId"
  | "siteId"
  | "headerPreset"
  | "templateCode"
  | "templateVersion"
  | "idempotencyKey"
  | "sourceFile"
  | "replaceMapFile"
  | "docxFile"
  | "preset"
  | "mapping"
  | "brandingPreview"
  | "batch"
  | "pipelineRun"
>;

export const useWizardStepActions = (deps: ActionDeps) => {
  const handleSourceFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      toast.error("Файл слишком большой (лимит 10MB)");
      return;
    }
    deps.setSourceFile(file);
    deps.setPartial({ sourceFileName: file.name });
    if (file.name.endsWith(".csv")) {
      const columns = await parseCsvColumns(file);
      deps.setPartial({ sourceColumns: columns });
    }
  };

  const handleBrandingPreview = async () => {
    try {
      if (!deps.companyId) return;
      const preview = await previewBranding({
        company_id: deps.companyId,
        site_id: deps.siteId || undefined,
        preset_code: deps.headerPreset || undefined,
        document_title: deps.templateCode || "Branded document",
        document_number: `preview-${deps.templateVersion}`,
        watermark_override: { enabled: true, text: "PREVIEW" },
      });
      deps.pushBrandingPreview(preview);
      deps.setPartial({
        companyId: (preview.wizard_defaults.company_id as string | undefined) ?? deps.companyId,
        siteId: (preview.wizard_defaults.site_id as string | undefined) ?? deps.siteId,
        headerPreset: (preview.wizard_defaults.preset_code as string | undefined) ?? deps.headerPreset,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось собрать branded preview");
    }
  };

  const handleReplaceMapFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    deps.setReplaceMapFile(file);
    deps.setPartial({ replaceMapFileName: file?.name ?? "" });
  };

  const handleReplaceDryRun = async () => {
    try {
      if (!deps.docxFile || !deps.replaceMapFile) return;
      const result = await replaceDryRun({ docxFile: deps.docxFile, replaceMapFile: deps.replaceMapFile, idempotencyKey: deps.idempotencyKey });
      deps.setPartial({ replaceDryRun: result });
      const fullReport = await getReplaceReport(result.report_id, { limit: 100 });
      deps.setPartial({ replaceDryRun: { ...result, preview_samples: fullReport.rows } });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось выполнить dry-run replace");
    }
  };

  const handleRunBatch = async () => {
    try {
      if (!deps.sourceFile) return;
      const response = await generateDocumentsBatch({
        file: deps.sourceFile,
        templateCode: deps.templateCode,
        templateVersion: deps.templateVersion,
        companyId: deps.companyId,
      });
      deps.setPartial({ batch: response });
      toast.success("Batch запущен");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось запустить batch");
    }
  };

  const handleRunSinglePipeline = async () => {
    try {
      const payload = {
        template_code: deps.templateCode,
        template_version: deps.templateVersion,
        company_id: deps.companyId,
        data: {
          preset: deps.preset,
          mapping: deps.mapping,
          headerPreset: deps.headerPreset,
          siteId: deps.siteId || null,
          branding_preview: deps.brandingPreview?.apply_headers_payload ?? null,
          reproducibility: deps.brandingPreview?.profile.reproducibility ?? null,
        },
      };
      const task = await generateDocument(payload, deps.idempotencyKey);
      const status = await getGenerationTaskStatus(task.task_id);
      deps.setPartial({ taskId: task.task_id });
      const run = await getPipelineRun(task.task_id);
      deps.setPartial({ pipelineRun: run });
      if (status.status === "failed" || status.status === "error") {
        toast.error(status.error ?? "Pipeline завершился с ошибкой");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось запустить single pipeline");
    }
  };

  const handleOpenFirstArtifact = async () => {
    try {
      const fileId = String((deps.pipelineRun?.artifacts?.all as Array<{ file_id?: string }> | undefined)?.[0]?.file_id ?? "");
      if (!fileId) {
        toast.error("Файл артефакта не найден.");
        return;
      }
      const link = await fetchFileDownloadLink(fileId);
      window.open(link.url, "_blank", "noopener,noreferrer");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось скачать артефакт");
    }
  };

  return {
    handleSourceFileChange,
    handleBrandingPreview,
    handleReplaceMapFileChange,
    handleReplaceDryRun,
    handleRunBatch,
    handleRunSinglePipeline,
    handleOpenFirstArtifact,
  };
};
