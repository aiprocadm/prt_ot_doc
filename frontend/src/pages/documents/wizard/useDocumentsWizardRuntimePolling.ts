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
  usePolling(
    async () => {
      const run = await getPipelineRun(taskId);
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
      onBatch(updated);
    },
    3000,
    {
      enabled: Boolean(batch?.id && tenantSlug && ["queued", "running"].includes(batch.status)),
      onError: () => toast.error("Не удалось обновить batch статус.")
    }
  );
};
