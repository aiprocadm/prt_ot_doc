import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn()
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: getMock
  }
}));

import ClientPortalHistoryPage from "@/pages/client-portal/ClientPortalHistoryPage";
import ClientPortalRequestsPage from "@/pages/client-portal/ClientPortalRequestsPage";

const setupApi = () => {
  getMock.mockImplementation((url: string) => {
    if (url === "/client-portal/packages") {
      return Promise.resolve({ data: [{ id: "run-1", status: "published", started_at: "2026-03-18T10:00:00Z" }] });
    }
    return Promise.resolve({
      data: {
        run: { id: "run-1", status: "published" },
        history: { status_flow: ["running", "published"], events_count: 2, tickets_count: 1, requirements_total: 3, requirements_missing: 1 },
        files: [],
        events: [{ id: "evt-1", type: "package_run.published", created_at: "2026-03-18T11:00:00Z" }],
        tickets: [{ id: "ticket-1", title: "Нужна уточняющая справка", status: "open", created_at: "2026-03-18T12:00:00Z" }]
      }
    });
  });
};

describe("client portal pages", () => {
  it("renders history from package details API", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <ClientPortalHistoryPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("События пакета")).toBeInTheDocument());
    expect(screen.getByText(/package_run.published/i)).toBeInTheDocument();
  });

  it("renders requests from package details API", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <ClientPortalRequestsPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Запросы и обращения")).toBeInTheDocument());
    expect(screen.getByText(/Нужна уточняющая справка/i)).toBeInTheDocument();
  });
});
