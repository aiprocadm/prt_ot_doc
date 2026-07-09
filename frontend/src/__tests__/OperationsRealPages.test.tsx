import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminPage from "@/pages/admin/AdminPage";
import ContractorsPage from "@/pages/contractors/ContractorsPage";
import MedicalPage from "@/pages/medical/MedicalPage";
import SettingsPage from "@/pages/settings/SettingsPage";

const operationsApiMock = vi.hoisted(() => ({
  getContractorSnapshot: vi.fn(),
  getSettingsSnapshot: vi.fn(),
  getMedicalSnapshot: vi.fn(),
  getAdminSnapshot: vi.fn(),
  getPsychiatricSnapshot: vi.fn(),
  seedPsychiatricDefaults: vi.fn(),
  getMedicalOversightSnapshot: vi.fn(),
  downloadContingentRegisterPrint: vi.fn(),
  downloadNamedListPrint: vi.fn(),
  listMedicalReferrals: vi.fn(),
  createMedicalReferral: vi.fn(),
  transitionMedicalReferral: vi.fn(),
  generateMedicalReferrals: vi.fn(),
  listMedicalSuspensions: vi.fn(),
  liftMedicalSuspension: vi.fn()
}));

vi.mock("@/api/operations", () => ({ operationsApi: operationsApiMock }));
vi.mock("@/permissions/useAbility", () => ({ useAbility: () => ({ can: () => true }) }));

describe("real-data operational pages", () => {
  beforeEach(() => {
    Object.values(operationsApiMock).forEach((mock) => mock.mockReset());
  });

  it("renders contractors registry from companies/sites/contracts snapshot", async () => {
    operationsApiMock.getContractorSnapshot.mockResolvedValue({
      companies: [{ id: "ctr-1", name: "ООО Альфа Подряд", status: "active", company_id: "c-1" }],
      hostCompanies: [{ id: "c-1", name: "ООО Альфа", activity_type: "Монтаж", hazardous_factors: ["noise"] }],
      sites: [{ id: "s-1", company_id: "c-1", name: "Площадка 1" }],
      contracts: [{ id: "ctr-1", company_id: "c-1", status: "active" }],
      employees: [],
      incidents: [],
      complianceSummary: { employees_total: 0, admission: {}, training: {}, medical: {} }
    });

    render(
      <MemoryRouter>
        <ContractorsPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("ООО Альфа Подряд")).toBeInTheDocument();
    expect(screen.getAllByText("ООО Альфа").length).toBeGreaterThan(0);
    expect(screen.getByText("Низкий")).toBeInTheDocument();
  });

  it("renders tenant settings snapshot instead of placeholder copy", async () => {
    operationsApiMock.getSettingsSnapshot.mockResolvedValue({
      tenancy: { tenant: { id: "t-1", slug: "demo", code: "DMO", schema_name: "tenant_demo" }, quota: { max_parallel_jobs: 4, max_doc_generations_per_month: 500 }, usage: { doc_generations: 12 }, correlation_id: "corr-1" },
      notifications: { email_enabled: true, telegram_enabled: false, reminder_window_days: 7 },
      apiTokens: [{ id: "tok-1", name: "ci", scopes: ["documents:read"], created_at: "2026-03-21T00:00:00Z", is_revoked: false }]
    });

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    );

    expect(await screen.findAllByText("demo")).toHaveLength(2);
    expect(screen.getByText("corr-1")).toBeInTheDocument();
    expect(screen.getByText("Включен")).toBeInTheDocument();
  });

  it("renders medical registry from backend medical exams endpoint", async () => {
    operationsApiMock.getMedicalSnapshot.mockResolvedValue({
      exams: [{ id: "m-1", person_id: "p-1", exam_type: "Предварительный", exam_date: "2026-03-01", valid_until: "2026-12-31", conclusion: "Годен", created_at: "2026-03-01T00:00:00Z", updated_at: "2026-03-01T00:00:00Z" }],
      persons: [{ id: "p-1", full_name: "Иванов И.И.", first_name: "Иван", last_name: "Иванов", status: "active", created_at: "2026-03-01T00:00:00Z", updated_at: "2026-03-01T00:00:00Z" }],
      tasks: []
    });
    operationsApiMock.getPsychiatricSnapshot.mockResolvedValue({ activityTypes: [], contingent: [] });
    operationsApiMock.getMedicalOversightSnapshot.mockResolvedValue({
      summary: { by_status: {}, total: 0, overdue_count: 0, suspended_count: 0 },
      register: [],
      namedList: [],
    });
    operationsApiMock.listMedicalReferrals.mockResolvedValue([]);
    operationsApiMock.listMedicalSuspensions.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <MedicalPage />
      </MemoryRouter>
    );

    expect((await screen.findAllByText("Иванов И.И.")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Предварительный").length).toBeGreaterThan(0);
    expect(screen.getByText("Годен")).toBeInTheDocument();
  });

  it("renders admin operational console cards", async () => {
    operationsApiMock.getAdminSnapshot.mockResolvedValue({
      tenancy: { tenant: { id: "t-1", slug: "demo" } },
      outbox: [{ id: "o-1", event_type: "document.ready", status: "pending", destination: "webhook", attempts: 1, created_at: "2026-03-21T00:00:00Z" }],
      webhooks: [{ id: "w-1", code: "main", target_url: "https://example.test", is_active: true }],
      apiTokens: [{ id: "tok-1", name: "ci", scopes: [], created_at: "2026-03-21T00:00:00Z", is_revoked: false }],
      auditItems: [{ id: "a-1", action: "update", object_type: "tenant", created_at: "2026-03-21T00:00:00Z" }]
    });

    render(
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/document.ready/)).toBeInTheDocument();
    expect(screen.getByText(/main/)).toBeInTheDocument();
    expect(screen.getByText(/update · tenant/)).toBeInTheDocument();
  });
});
