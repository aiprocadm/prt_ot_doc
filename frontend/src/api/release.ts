import { apiClient } from "@/api/client";

export type ReleaseStatus = {
  approval: string;
  signature: string;
  edo: string;
};

export const releaseApi = {
  documentReleaseStatus: async (
    documentVersionId: string,
  ): Promise<ReleaseStatus> => {
    const [approval, signature, edo] = await Promise.all([
      apiClient.get<{ items: Array<{ status: string }> }>(
        "/v1/approvals/instances",
        { params: { document_version_id: documentVersionId } },
      ),
      apiClient.get<{ items: Array<{ status: string }> }>("/v1/sign/status", {
        params: { document_version_id: documentVersionId },
      }),
      apiClient.get<{ items: Array<{ status: string }> }>("/v1/edo/messages", {
        params: { document_version_id: documentVersionId },
      }),
    ]);
    return {
      approval: approval.data.items[0]?.status ?? "draft",
      signature: signature.data.items[0]?.status ?? "pending",
      edo: edo.data.items[0]?.status ?? "queued",
    };
  },
  quickApprove: async (taskId: string, comment?: string) =>
    apiClient.post(`/v1/approvals/tasks/${taskId}/decision`, {
      decision: "approve",
      comment,
    }),
  quickReject: async (taskId: string, comment?: string) =>
    apiClient.post(`/v1/approvals/tasks/${taskId}/decision`, {
      decision: "reject",
      comment,
    }),
  quickSign: async (documentVersionId: string) =>
    apiClient.post("/v1/sign/submit", {
      document_version_id: documentVersionId,
      kind: "un_ep",
      signed_blob: "dev-stub-signature",
      cert_info: {
        serial: "DEV-SERIAL",
        valid_from: "2024-01-01",
        valid_to: "2030-01-01",
        ocsp_status: "unknown",
      },
    }),
};
