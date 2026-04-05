import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminPage from "@/pages/admin/AdminPage";

const getAdminSnapshotMock = vi.fn();

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getAdminSnapshot: (...args: unknown[]) => getAdminSnapshotMock(...args)
  }
}));

vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => ({
    can: () => true
  })
}));

describe("AdminPage", () => {
  beforeEach(() => {
    getAdminSnapshotMock.mockReset();
  });

  it("renders enterprise diagnostics widgets from live snapshot", async () => {
    getAdminSnapshotMock.mockResolvedValue({
      tenancy: { tenant: { id: "tenant-1", slug: "corp" } },
      outbox: [{ id: "o1", event_type: "doc.created", status: "pending", attempts: 1 }],
      webhooks: [],
      apiTokens: [],
      auditItems: [],
      integrationReadiness: null,
      attention: null,
      taskInbox: null,
      providerStatus: {
        production_ready: false,
        blocking_for_golive: ["signing"],
        providers: [{ name: "signing", mode: "non_production", adapter: "internal-fallback" }]
      },
      tenantHealth: {
        score: 88,
        grade: "B",
        failed_jobs_last24h: 1,
        outbox_events_poisoned: 0
      },
      roleSummary: {
        role: "admin",
        open_tasks: 5,
        overdue_tasks: 2,
        overdue_deadlines: 1
      }
    });

    render(
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("Оценка здоровья тенанта")).toBeInTheDocument();
    expect(screen.getByText("Score: 88 / 100")).toBeInTheDocument();
    expect(screen.getByText("Role: admin")).toBeInTheDocument();
    expect(screen.getByText("Blocking providers: 1")).toBeInTheDocument();
  });
});
