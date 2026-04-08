import { useRef } from "react";
import { toast } from "sonner";

import { getDocumentBatch } from "@/api/documents";
import { getPipelineRun } from "@/api/pipelines";
import { usePolling } from "@/hooks/usePolling";
import type { DocumentBatchRun } from "@/api/documents";
import type { PipelineRun } from "@/api/pipelines";

type RuntimePollingParams = {
  tenantSlug?: string;
  taskId: string;
  pipelineRun: PipelineRun | null;
  batch: DocumentBatchRun | null;
  onPipelineRun: (run: PipelineRun) => void;
  onBatch: (batch: DocumentBatchRun) => void;
};

export const useDocumentsWizardRuntimePolling = ({ tenantSlug, taskId, pipelineRun, batch, onPipelineRun, onBatch }: RuntimePollingParams) => {
  const lastRunSignatureRef = useRef<string>("");
  const lastBatchSignatureRef = useRef<string>("");

  usePolling(
    async () => {
      const run = await getPipelineRun(taskId);
      const nextSignature = JSON.stringify({
        run_id: run.run_id,
        status: run.status,
        step_runs: run.step_runs.map((step) => ({
          step_run_id: step.step_run_id,
          step_code: step.step_code,
          attempt: step.attempt,
          status: step.status,
          error_code: step.error_code,
          started_at: step.started_at,
          ended_at: step.ended_at
        }))
      });
      if (nextSignature === lastRunSignatureRef.current) return;
      lastRunSignatureRef.current = nextSignature;
      onPipelineRun(run);
    },
    3000,
    {
      enabled: Boolean(taskId && tenantSlug && (!pipelineRun || ["queued", "running"].includes(pipelineRun.status))),
      onError: () => toast.error("Не удалось обновить timeline job.")
    }
  );

  usePolling(
    async () => {
      if (!batch?.id) return;
      const updated = await getDocumentBatch(batch.id);
      const nextSignature = JSON.stringify({
        id: updated.id,
        status: updated.status,
        total: updated.total,
        processed: updated.processed,
        succeeded: updated.succeeded,
        failed: updated.failed,
        items: updated.items.map((item) => ({
          id: item.id,
          row_index: item.row_index,
          status: item.status,
          error: item.error,
          document_id: item.document_id,
          document_version_id: item.document_version_id
        }))
      });
      if (nextSignature === lastBatchSignatureRef.current) return;
      lastBatchSignatureRef.current = nextSignature;
      onBatch(updated);
    },
    3000,
    {
      enabled: Boolean(batch?.id && tenantSlug && ["queued", "running"].includes(batch.status)),
      onError: () => toast.error("Не удалось обновить batch статус.")
    }
  );
};
