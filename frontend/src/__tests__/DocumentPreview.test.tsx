import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocumentPreview } from "@/features/documents/DocumentPreview";

vi.mock("@/stores/documents", () => ({
  useDocumentsStore: () => ({
    refreshStatus: vi.fn(),
    download: vi.fn(),
  }),
}));

vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => ({
    can: () => true,
  }),
}));

const quickSignSpy = vi.fn().mockResolvedValue({});

vi.mock("@/api/release", () => ({
  releaseApi: {
    documentReleaseStatus: vi
      .fn()
      .mockResolvedValue({
        approval: "approved",
        signature: "pending",
        edo: "queued",
      }),
    quickApprove: vi.fn(),
    quickReject: vi.fn(),
    quickSign: (...args: unknown[]) => quickSignSpy(...args),
  },
}));

vi.mock("@/api/approvals", () => ({
  approvalsApi: {
    listMyTasks: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("@/api/documents", () => ({
  getDocumentReadiness: vi.fn().mockResolvedValue({
    score: 82,
    blockers: [],
    recommended_actions: ["Завершите согласование по маршруту"],
  }),
}));

vi.mock("@/utils/download", () => ({
  downloadBlob: vi.fn(),
}));

describe("DocumentPreview", () => {
  it("renders timeline statuses and uses production wording for sign action", async () => {
    render(
      <DocumentPreview
        document={
          {
            id: "doc-1",
            current_version_id: "ver-1",
            name: "Приказ",
            type: "order",
            version: 3,
            status: "ready",
            updated_at: "2025-01-01T00:00:00Z",
            storage: null,
            history: [],
          } as never
        }
      />,
    );

    await waitFor(() =>
      expect(screen.getByText("approved")).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByTestId("document-readiness-panel")).toHaveTextContent(
        "82%",
      ),
    );
    expect(screen.getByRole("tab", { name: "Хронология" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Подписать" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Подписать" }));
    await waitFor(() => expect(quickSignSpy).toHaveBeenCalledWith("ver-1"));
  });
});
