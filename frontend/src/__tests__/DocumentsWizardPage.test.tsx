import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { useTenantStore } from "@/stores/tenant";
import { useDocumentsWizardStore } from "@/stores/documentsWizard";

vi.mock("@/api/documents", () => ({
  generateDocument: vi.fn(),
  generateDocumentsBatch: vi.fn(),
  getDocumentBatch: vi.fn(),
  getGenerationTaskStatus: vi.fn(),
  getReplaceReport: vi.fn(),
  replaceDryRun: vi.fn()
}));

vi.mock("@/api/pipelines", () => ({
  getPipelineRun: vi.fn()
}));

vi.mock("@/api/files", () => ({
  fetchFileDownloadLink: vi.fn()
}));

import DocumentsWizardPage from "@/pages/documents/DocumentsWizardPage";

describe("DocumentsWizardPage", () => {
  it("blocks api flow without tenant", async () => {
    useDocumentsWizardStore.getState().reset();
    useDocumentsWizardStore.setState({ step: 1 });
    useTenantStore.setState({ tenant: null, tenants: [], setTenant: vi.fn(), clearTenant: vi.fn() });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <DocumentsWizardPage />
      </MemoryRouter>
    );

    expect(screen.getByText(/без x-tenant запросы заблокированы/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /далее/i }));
    expect(await screen.findByRole("heading", { name: /шаг 2: файл/i })).toBeInTheDocument();
  });

  it("shows archive readiness summary and real navigation actions instead of placeholder button", () => {
    useDocumentsWizardStore.getState().reset();
    useDocumentsWizardStore.setState({
      step: 10,
      batch: {
        id: "batch-1",
        status: "completed",
        total: 0,
        processed: 0,
        succeeded: 0,
        failed: 0,
        items: []
      },
      pipelineRun: {
        run_id: "run-1",
        status: "done",
        step_runs: [],
        artifacts: null
      }
    });
    useTenantStore.setState({
      tenant: { slug: "demo", name: "Demo tenant" } as never,
      tenants: [],
      setTenant: vi.fn(),
      clearTenant: vi.fn()
    });

    render(
      <MemoryRouter>
        <DocumentsWizardPage />
      </MemoryRouter>
    );

    expect(screen.getByText(/архив готов к публикации/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /перейти в архив/i })).toHaveAttribute("href", "/archive");
    expect(screen.getByRole("link", { name: /открыть согласование \/ подпись/i })).toHaveAttribute(
      "href",
      "/approvals"
    );
    expect(screen.queryByRole("button", { name: /mvp placeholder/i })).not.toBeInTheDocument();
  });
});
