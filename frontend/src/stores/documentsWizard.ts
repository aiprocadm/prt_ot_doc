import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { BrandingPreviewDto } from "@/api/branding";
import type {
  DocumentBatchRun,
  MappingValidationResponse,
  ReplaceDryRunResponse,
} from "@/api/documents";
import type { PipelineRun } from "@/api/pipelines";
import type { QualityReport } from "@/types/dto/documentQuality";

type RowStatusFilter = "all" | "success" | "failed";
type QuickGenerationHistoryItem = {
  id: string;
  createdAt: string;
  personId: string;
  companyId: string;
  siteId: string;
  caseType: string;
  templateCode: string;
  templateVersion: number;
  taskId: string;
  status: string;
};

const getPreviewHistoryKey = (preview: BrandingPreviewDto) => {
  const generatedAt = String(
    preview.profile.reproducibility?.generated_at ?? "",
  );
  const companyId = preview.profile.company_id;
  const siteId = preview.profile.site_id ?? "";
  const presetCode = preview.preset_code ?? "";
  return [companyId, siteId, presetCode, generatedAt].join("::");
};

export type DocumentsWizardState = {
  step: number;
  preset: string;
  companyId: string;
  siteId: string;
  sourceFileName: string;
  sourceColumns: string[];
  mapping: Record<string, string>;
  templateCode: string;
  templateVersion: number;
  headerPreset: string;
  headerOptions: Record<string, string>;
  replaceMapFileName: string;
  replaceDryRun: ReplaceDryRunResponse | null;
  mappingValidation: MappingValidationResponse | null;
  qualityReport: QualityReport | null;
  batch: DocumentBatchRun | null;
  taskId: string;
  pipelineRun: PipelineRun | null;
  brandingPreview: BrandingPreviewDto | null;
  brandingPreviewHistory: BrandingPreviewDto[];
  idempotencyKey: string;
  rowStatusFilter: RowStatusFilter;
  quickGenerationHistory: QuickGenerationHistoryItem[];
  pushBrandingPreview: (preview: BrandingPreviewDto) => void;
  pushQuickGenerationHistory: (entry: QuickGenerationHistoryItem) => void;
  setPartial: (next: Partial<DocumentsWizardState>) => void;
  reset: () => void;
};

const createIdempotencyKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const baseState = {
  step: 1,
  preset: "manual",
  companyId: "",
  siteId: "",
  sourceFileName: "",
  sourceColumns: [],
  mapping: {},
  templateCode: "",
  templateVersion: 1,
  headerPreset: "default",
  headerOptions: {},
  replaceMapFileName: "",
  replaceDryRun: null,
  mappingValidation: null,
  qualityReport: null,
  batch: null,
  taskId: "",
  pipelineRun: null,
  brandingPreview: null,
  brandingPreviewHistory: [],
  idempotencyKey: createIdempotencyKey(),
  rowStatusFilter: "all" as RowStatusFilter,
  quickGenerationHistory: [],
};

export const useDocumentsWizardStore = create<DocumentsWizardState>()(
  persist(
    (set) => ({
      ...baseState,
      pushBrandingPreview: (preview) =>
        set((state) => ({
          ...state,
          brandingPreview: preview,
          brandingPreviewHistory: [preview, ...state.brandingPreviewHistory]
            .filter(
              (item, index, items) =>
                items.findIndex(
                  (candidate) =>
                    getPreviewHistoryKey(candidate) ===
                    getPreviewHistoryKey(item),
                ) === index,
            )
            .slice(0, 5),
        })),
      pushQuickGenerationHistory: (entry) =>
        set((state) => ({
          ...state,
          quickGenerationHistory: [entry, ...state.quickGenerationHistory]
            .filter(
              (item, index, items) =>
                items.findIndex((candidate) => candidate.id === item.id) ===
                index,
            )
            .slice(0, 10),
        })),
      setPartial: (next) => set((state) => ({ ...state, ...next })),
      reset: () =>
        set({ ...baseState, idempotencyKey: createIdempotencyKey() }),
    }),
    {
      name: "documents-wizard-v1",
      partialize: (state) => ({
        step: state.step,
        preset: state.preset,
        companyId: state.companyId,
        siteId: state.siteId,
        sourceFileName: state.sourceFileName,
        sourceColumns: state.sourceColumns,
        mapping: state.mapping,
        templateCode: state.templateCode,
        templateVersion: state.templateVersion,
        headerPreset: state.headerPreset,
        headerOptions: state.headerOptions,
        replaceMapFileName: state.replaceMapFileName,
        mappingValidation: state.mappingValidation,
        qualityReport: state.qualityReport,
        brandingPreview: state.brandingPreview,
        brandingPreviewHistory: state.brandingPreviewHistory,
        idempotencyKey: state.idempotencyKey,
        rowStatusFilter: state.rowStatusFilter,
        quickGenerationHistory: state.quickGenerationHistory,
      }),
    },
  ),
);
