import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BillingPage from "@/pages/admin/BillingPage";
import IntegrationsPage from "@/pages/integrations/IntegrationsPage";
import PipelineRuns from "@/pages/PipelineRuns";

const apiGetMock = vi.fn();
const listPipelineRunsMock = vi.fn();
const getBillingSummaryMock = vi.fn();
const getBillingInvoicesMock = vi.fn();
const getBillingPlansMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => apiGetMock(...args),
    post: vi.fn(),
  },
}));

vi.mock("@/api/pipelines", () => ({
  listPipelineRuns: (...args: unknown[]) => listPipelineRunsMock(...args),
  bulkActionPipelineRuns: vi.fn(),
}));

vi.mock("@/api/billing", () => ({
  getBillingSummary: (...args: unknown[]) => getBillingSummaryMock(...args),
  getBillingInvoices: (...args: unknown[]) => getBillingInvoicesMock(...args),
  getBillingPlans: (...args: unknown[]) => getBillingPlansMock(...args),
  changeBillingPlan: vi.fn(),
  markSubscriptionPastDue: vi.fn(),
  markSubscriptionPaid: vi.fn(),
  suspendSubscription: vi.fn(),
  activateSubscription: vi.fn(),
}));

describe("operational hardening states", () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    listPipelineRunsMock.mockReset();
    getBillingSummaryMock.mockReset();
    getBillingInvoicesMock.mockReset();
    getBillingPlansMock.mockReset();
  });

  it("renders integrations diagnostics surface when outbox and events are absent", async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url === "/admin/outbox") return Promise.resolve({ data: { items: [] } });
      if (url === "/admin/outbox/events") return Promise.resolve({ data: { items: [] } });
      if (url === "/integrations/readiness") {
        return Promise.resolve({ data: { providers: [], webhooks: { configured_total: 0, enabled_total: 0, delivery_failed_total: 0 } } });
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });

    render(<IntegrationsPage />);

    expect(await screen.findByText("Готовность провайдеров")).toBeInTheDocument();
    expect(screen.getByText("История исходящих доставок")).toBeInTheDocument();
  });

  it("renders billing page gracefully when summary is unavailable", async () => {
    getBillingSummaryMock.mockResolvedValue(null);
    getBillingInvoicesMock.mockResolvedValue([]);
    getBillingPlansMock.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <BillingPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("Тариф и статус")).toBeInTheDocument();
    expect(screen.getByText("Счета пока не выставлялись.")).toBeInTheDocument();
  });

  it("shows empty pipeline runs state", async () => {
    listPipelineRunsMock.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <PipelineRuns />
      </MemoryRouter>
    );

    expect(await screen.findByText("Пайплайны не найдены")).toBeInTheDocument();
  });
});
