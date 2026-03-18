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

import ClientPortalPackagesPage from "@/pages/client-portal/ClientPortalPackagesPage";

describe("ClientPortalPackagesPage", () => {
  it("loads packages and renders selected package details", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/client-portal/packages") {
        return Promise.resolve({ data: [{ id: "run-1", status: "published", started_at: "2026-03-18T10:00:00Z" }] });
      }
      return Promise.resolve({
        data: {
          run: { id: "run-1", status: "published" },
          history: { status_flow: ["running", "published"], events_count: 2, tickets_count: 1, requirements_total: 3, requirements_missing: 1 },
          files: [{ kind: "zip", signed_url: "memory://signed/file", sha256: "abc", size: 128 }],
          events: [{ id: "evt-1", type: "package_run.published", created_at: "2026-03-18T11:00:00Z" }],
          tickets: []
        }
      });
    });

    render(
      <MemoryRouter>
        <ClientPortalPackagesPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Список пакетов")).toBeInTheDocument();
    });
    expect(screen.getAllByText("run-1")).toHaveLength(2);
    expect(screen.getByText(/package_run.published/i)).toBeInTheDocument();
    expect(screen.getByText(/SHA256: abc/i)).toBeInTheDocument();
  });
});
