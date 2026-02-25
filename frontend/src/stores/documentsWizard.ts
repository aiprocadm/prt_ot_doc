import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { DocumentBatchRun, ReplaceDryRunResponse } from "@/api/documents";
import type { PipelineRun } from "@/api/pipelines";

type RowStatusFilter = "all" | "success" | "failed";

export type DocumentsWizardState = {
  step: number;
  preset: string;
  companyId: string;
  sourceFileName: string;
  sourceColumns: string[];
  mapping: Record<string, string>;
  templateCode: string;
  templateVersion: number;
  headerPreset: string;
  headerOptions: Record<string, string>;
  replaceMapFileName: string;
  replaceDryRun: ReplaceDryRunResponse | null;
  batch: DocumentBatchRun | null;
  taskId: string;
  pipelineRun: PipelineRun | null;
  idempotencyKey: string;
  rowStatusFilter: RowStatusFilter;
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
  sourceFileName: "",
  sourceColumns: [],
  mapping: {},
  templateCode: "",
  templateVersion: 1,
  headerPreset: "default",
  headerOptions: {},
  replaceMapFileName: "",
  replaceDryRun: null,
  batch: null,
  taskId: "",
  pipelineRun: null,
  idempotencyKey: createIdempotencyKey(),
  rowStatusFilter: "all" as RowStatusFilter
};

export const useDocumentsWizardStore = create<DocumentsWizardState>()(
  persist(
    (set) => ({
      ...baseState,
      setPartial: (next) => set((state) => ({ ...state, ...next })),
      reset: () => set({ ...baseState, idempotencyKey: createIdempotencyKey() })
    }),
    {
      name: "documents-wizard-v1",
      partialize: (state) => ({
        step: state.step,
        preset: state.preset,
        companyId: state.companyId,
        sourceFileName: state.sourceFileName,
        sourceColumns: state.sourceColumns,
        mapping: state.mapping,
        templateCode: state.templateCode,
        templateVersion: state.templateVersion,
        headerPreset: state.headerPreset,
        headerOptions: state.headerOptions,
        replaceMapFileName: state.replaceMapFileName,
        idempotencyKey: state.idempotencyKey,
        rowStatusFilter: state.rowStatusFilter
      })
    }
  )
);
