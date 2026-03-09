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
});
