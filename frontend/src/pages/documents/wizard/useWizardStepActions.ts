import type { ChangeEvent } from "react";
import { toast } from "sonner";

import { fetchFileDownloadLink } from "@/api/files";
import {
  checkDocumentQuality,
  generateDocument,
  generateDocumentsBatch,
  getGenerationTaskStatus,
  validateDocumentMapping,
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
  const handleSourceFileChange = async (
    event: ChangeEvent<HTMLInputElement>,
  ) => {
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
      return;
    }
    deps.setPartial({ sourceColumns: [] });
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
        companyId:
          (preview.wizard_defaults.company_id as string | undefined) ??
          deps.companyId,
        siteId:
          (preview.wizard_defaults.site_id as string | undefined) ??
          deps.siteId,
        headerPreset:
          (preview.wizard_defaults.preset_code as string | undefined) ??
          deps.headerPreset,
      });
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Не удалось собрать branded preview",
      );
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
      toast.error(
        error instanceof Error ? error.message : "Не удалось запустить batch",
      );
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
          reproducibility:
            deps.brandingPreview?.profile.reproducibility ?? null,
        },
      };
      const task = await generateDocument(payload, deps.idempotencyKey);
      const status = await getGenerationTaskStatus(task.task_id);
      const qualityReport = await checkDocumentQuality({
        data: payload.data,
        required_fields: [],
      });
      deps.setPartial({ taskId: task.task_id });
      const run = await getPipelineRun(task.task_id);
      deps.setPartial({ pipelineRun: run, qualityReport });
      if (status.status === "failed" || status.status === "error") {
        toast.error(status.error ?? "Pipeline завершился с ошибкой");
      }
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Не удалось запустить single pipeline",
      );
    }
  };

  const handleValidateMapping = async () => {
    try {
      const result = await validateDocumentMapping({
        source_fields: Object.keys(deps.mapping),
        mapping: deps.mapping,
        required_template_fields: [],
      });
      deps.setPartial({ mappingValidation: result });
      if (!result.ok) {
        toast.warning("Маппинг содержит незаполненные обязательные поля");
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Не удалось проверить маппинг",
      );
    }
  };

  const handleOpenFirstArtifact = async () => {
    try {
      const fileId = String(
        (
          deps.pipelineRun?.artifacts?.all as
            | Array<{ file_id?: string }>
            | undefined
        )?.[0]?.file_id ?? "",
      );
      if (!fileId) {
        toast.error("Файл артефакта не найден.");
        return;
      }
      const link = await fetchFileDownloadLink(fileId);
      window.open(link.url, "_blank", "noopener,noreferrer");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Не удалось скачать артефакт",
      );
    }
  };

  return {
    handleSourceFileChange,
    handleBrandingPreview,
    handleValidateMapping,
    handleRunBatch,
    handleRunSinglePipeline,
    handleOpenFirstArtifact,
  };
};
