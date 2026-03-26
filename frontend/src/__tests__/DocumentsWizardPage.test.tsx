import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";

import { useTenantStore } from "@/stores/tenant";
import { useDocumentsWizardStore } from "@/stores/documentsWizard";

const documentsApiMock = vi.hoisted(() => ({
  generateDocument: vi.fn(),
  generateDocumentsBatch: vi.fn(),
  getDocumentBatch: vi.fn(),
  getGenerationTaskStatus: vi.fn(),
  getReplaceReport: vi.fn(),
  replaceDryRun: vi.fn()
}));

const pipelinesApiMock = vi.hoisted(() => ({
  getPipelineRun: vi.fn()
}));

const brandingApiMock = vi.hoisted(() => ({
  getBrandingProfile: vi.fn(async () => ({
    scope: "company",
    preferred_header_preset_code: "company_brand"
  })),
  listLayoutPresets: vi.fn(async () => [{ id: "preset-1", code: "company_brand", name: "Company brand" }]),
  listSites: vi.fn(async () => [{ id: "site-1", company_id: "company-1", name: "Main site" }]),
  previewBranding: vi.fn(async () => ({
    preset_code: "company_brand",
    sections: { header_odd: "АО Тест / Main site", footer_odd: "ИНН 123" },
    profile: {
      scope: "site",
      reproducibility: { generated_at: "2026-03-19T00:00:00Z" },
      resolution: {
        scope_chain: ["tenant", "company", "site"],
        effective_preset_source: "site.branding.preferred_letterhead_preset"
      }
    },
    watermark: { text: "PREVIEW" },
    unresolved_placeholders: [],
    apply_headers_payload: { preset_code: "company_brand" },
    wizard_defaults: { company_id: "company-1", site_id: "site-1", preset_code: "company_brand" }
  }))
}));

vi.mock("@/api/documents", () => ({
  generateDocument: documentsApiMock.generateDocument,
  generateDocumentsBatch: documentsApiMock.generateDocumentsBatch,
  getDocumentBatch: documentsApiMock.getDocumentBatch,
  getGenerationTaskStatus: documentsApiMock.getGenerationTaskStatus,
  getReplaceReport: documentsApiMock.getReplaceReport,
  replaceDryRun: documentsApiMock.replaceDryRun
}));

vi.mock("@/api/pipelines", () => ({
  getPipelineRun: pipelinesApiMock.getPipelineRun
}));

vi.mock("@/api/branding", () => ({
  getBrandingProfile: brandingApiMock.getBrandingProfile,
  listLayoutPresets: brandingApiMock.listLayoutPresets,
  listSites: brandingApiMock.listSites,
  previewBranding: brandingApiMock.previewBranding
}));

vi.mock("@/api/files", () => ({
  fetchFileDownloadLink: vi.fn()
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn()
  }
}));

import DocumentsWizardPage from "@/pages/documents/DocumentsWizardPage";
import { useCompaniesStore } from "@/stores/companies";

describe("DocumentsWizardPage", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  beforeEach(() => {
    Object.values(documentsApiMock).forEach((mock) => mock.mockReset());
    Object.values(pipelinesApiMock).forEach((mock) => mock.mockReset());
    Object.values(brandingApiMock).forEach((mock) => mock.mockReset());
    vi.mocked(toast.success).mockReset();
    vi.mocked(toast.error).mockReset();

    brandingApiMock.getBrandingProfile.mockResolvedValue({
      scope: "company",
      preferred_header_preset_code: "company_brand"
    });
    brandingApiMock.listLayoutPresets.mockResolvedValue([{ id: "preset-1", code: "company_brand", name: "Company brand" }]);
    brandingApiMock.listSites.mockResolvedValue([{ id: "site-1", company_id: "company-1", name: "Main site" }]);
    brandingApiMock.previewBranding.mockResolvedValue({
      preset_code: "company_brand",
      sections: { header_odd: "АО Тест / Main site", footer_odd: "ИНН 123" },
      profile: {
        scope: "site",
        reproducibility: { generated_at: "2026-03-19T00:00:00Z" },
        resolution: {
          scope_chain: ["tenant", "company", "site"],
          effective_preset_source: "site.branding.preferred_letterhead_preset"
        }
      },
      watermark: { text: "PREVIEW" },
      unresolved_placeholders: [],
      apply_headers_payload: { preset_code: "company_brand" },
      wizard_defaults: { company_id: "company-1", site_id: "site-1", preset_code: "company_brand" }
    });
  });

  it("blocks api flow without tenant", async () => {
    useDocumentsWizardStore.getState().reset();
    useDocumentsWizardStore.setState({ step: 1 });
    useCompaniesStore.setState({ items: [], list: vi.fn(async () => undefined) } as never);
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
        status: "done",
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
        artifacts: undefined
      }
    });
    useTenantStore.setState({
      tenant: { slug: "demo", name: "Demo tenant" } as never,
      tenants: [],
      setTenant: vi.fn(),
      clearTenant: vi.fn()
    });
    useCompaniesStore.setState({ items: [{ id: "company-1", name: "АО Тест" }], list: vi.fn(async () => undefined) } as never);

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

  it("renders branding preview controls on step 5 and shows reproducibility snapshot", async () => {
    useDocumentsWizardStore.getState().reset();
    useDocumentsWizardStore.setState({
      step: 5,
      companyId: "company-1",
      templateCode: "outbound_cover",
      templateVersion: 3
    });
    useTenantStore.setState({
      tenant: { slug: "demo", name: "Demo tenant" } as never,
      tenants: [],
      setTenant: vi.fn(),
      clearTenant: vi.fn()
    });
    useCompaniesStore.setState({ items: [{ id: "company-1", name: "АО Тест" }], list: vi.fn(async () => undefined) } as never);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <DocumentsWizardPage />
      </MemoryRouter>
    );

    await user.click(screen.getByRole("button", { name: /собрать branded preview/i }));

    expect(await screen.findByText(/АО Тест \/ Main site/i)).toBeInTheDocument();
    expect(screen.getByText(/reproducibility snapshot/i)).toBeInTheDocument();
    expect(screen.getByText(/site.branding.preferred_letterhead_preset/i)).toBeInTheDocument();
    expect(screen.getAllByText(/company_brand/i).length).toBeGreaterThan(0);
    expect(useDocumentsWizardStore.getState().brandingPreview?.wizard_defaults.site_id).toBe("site-1");
    expect(useDocumentsWizardStore.getState().brandingPreviewHistory).toHaveLength(1);
    expect(useDocumentsWizardStore.getState().siteId).toBe("site-1");
  });

  it("keeps preview history unique when the same reproducibility snapshot is rebuilt", async () => {
    useDocumentsWizardStore.getState().reset();
    useDocumentsWizardStore.setState({
      step: 5,
      companyId: "company-1",
      templateCode: "outbound_cover",
      templateVersion: 3
    });
    useTenantStore.setState({
      tenant: { slug: "demo", name: "Demo tenant" } as never,
      tenants: [],
      setTenant: vi.fn(),
      clearTenant: vi.fn()
    });
    useCompaniesStore.setState({ items: [{ id: "company-1", name: "АО Тест" }], list: vi.fn(async () => undefined) } as never);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <DocumentsWizardPage />
      </MemoryRouter>
    );

    const previewButton = screen.getByRole("button", { name: /собрать branded preview/i });
    await user.click(previewButton);
    await screen.findByText(/АО Тест \/ Main site/i);
    await user.click(previewButton);

    const state = useDocumentsWizardStore.getState();
    expect(state.brandingPreviewHistory).toHaveLength(1);
    expect(state.brandingPreview?.wizard_defaults.preset_code).toBe("company_brand");
  });

  it("shows toast error when branded preview request fails", async () => {
    useDocumentsWizardStore.getState().reset();
    useDocumentsWizardStore.setState({
      step: 5,
      companyId: "company-1",
      templateCode: "outbound_cover",
      templateVersion: 3
    });
    useTenantStore.setState({
      tenant: { slug: "demo", name: "Demo tenant" } as never,
      tenants: [],
      setTenant: vi.fn(),
      clearTenant: vi.fn()
    });
    useCompaniesStore.setState({ items: [{ id: "company-1", name: "АО Тест" }], list: vi.fn(async () => undefined) } as never);
    brandingApiMock.previewBranding.mockRejectedValue(new Error("preview failed"));

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <DocumentsWizardPage />
      </MemoryRouter>
    );

    await user.click(screen.getByRole("button", { name: /собрать branded preview/i }));

    expect(await screen.findByText(/история появится после preview/i)).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith("preview failed");
  });

  it("shows toast error when single pipeline request fails", async () => {
    useDocumentsWizardStore.getState().reset();
    useDocumentsWizardStore.setState({
      step: 7,
      companyId: "company-1",
      templateCode: "outbound_cover",
      templateVersion: 2,
      headerPreset: "company_brand"
    });
    useTenantStore.setState({
      tenant: { slug: "demo", name: "Demo tenant" } as never,
      tenants: [],
      setTenant: vi.fn(),
      clearTenant: vi.fn()
    });
    useCompaniesStore.setState({ items: [{ id: "company-1", name: "АО Тест" }], list: vi.fn(async () => undefined) } as never);
    documentsApiMock.generateDocument.mockRejectedValue(new Error("single pipeline failed"));

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <DocumentsWizardPage />
      </MemoryRouter>
    );

    await user.click(screen.getByRole("button", { name: /запустить single pipeline/i }));

    expect(toast.error).toHaveBeenCalledWith("single pipeline failed");
    expect(useDocumentsWizardStore.getState().pipelineRun).toBeNull();
  });

  it("polls queued pipeline run and updates store status", async () => {
    vi.useFakeTimers();

    useDocumentsWizardStore.getState().reset();
    useDocumentsWizardStore.setState({
      step: 7,
      taskId: "task-1",
      pipelineRun: {
        run_id: "task-1",
        status: "queued",
        step_runs: []
      }
    });
    useTenantStore.setState({
      tenant: { slug: "demo", name: "Demo tenant" } as never,
      tenants: [],
      setTenant: vi.fn(),
      clearTenant: vi.fn()
    });
    useCompaniesStore.setState({ items: [{ id: "company-1", name: "АО Тест" }], list: vi.fn(async () => undefined) } as never);
    pipelinesApiMock.getPipelineRun.mockResolvedValue({
      run_id: "task-1",
      status: "done",
      step_runs: []
    });

    render(
      <MemoryRouter>
        <DocumentsWizardPage />
      </MemoryRouter>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(pipelinesApiMock.getPipelineRun).toHaveBeenCalledWith("task-1");
    expect(useDocumentsWizardStore.getState().pipelineRun?.status).toBe("done");
  });

  it("shows toast when batch polling fails", async () => {
    vi.useFakeTimers();

    useDocumentsWizardStore.getState().reset();
    useDocumentsWizardStore.setState({
      step: 8,
      batch: {
        id: "batch-1",
        status: "running",
        total: 1,
        processed: 0,
        succeeded: 0,
        failed: 0,
        items: []
      }
    });
    useTenantStore.setState({
      tenant: { slug: "demo", name: "Demo tenant" } as never,
      tenants: [],
      setTenant: vi.fn(),
      clearTenant: vi.fn()
    });
    useCompaniesStore.setState({ items: [{ id: "company-1", name: "АО Тест" }], list: vi.fn(async () => undefined) } as never);
    documentsApiMock.getDocumentBatch.mockRejectedValue(new Error("batch poll failed"));

    render(
      <MemoryRouter>
        <DocumentsWizardPage />
      </MemoryRouter>
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(documentsApiMock.getDocumentBatch).toHaveBeenCalledWith("batch-1");
    expect(toast.error).toHaveBeenCalledWith("Не удалось обновить batch статус.");
  });
});
