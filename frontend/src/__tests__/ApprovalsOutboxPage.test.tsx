import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ApprovalsOutboxPage from "@/pages/approvals/ApprovalsOutboxPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

describe("ApprovalsOutboxPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    useAuthStore.setState({
      user: {
        id: "user-1",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "user@example.com",
        full_name: "User",
        roles: ["ot_specialist"],
        permissions: [PERMISSIONS.DOCUMENT_VIEW, PERMISSIONS.ADMIN_OUTBOX_MANAGE],
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });
  });

  it("shows empty state when approval outbox has no items", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/admin/outbox") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "other-1",
                event_type: "workflow.started",
                destination: "webhook://ops",
                status: "sent",
                attempts: 1,
                created_at: "2026-03-24T10:00:00Z",
              },
            ],
          },
        });
      }
      if (url === "/admin/outbox/events") {
        return Promise.resolve({ data: { items: [] } });
      }
      throw new Error(`Unexpected GET ${url}`);
    });

    render(
      <MemoryRouter>
        <ApprovalsOutboxPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/исходящие согласования пока отсутствуют/i)).toBeInTheDocument();
  });

  it("shows approval outbox rows and retry actions", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/admin/outbox") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "delivery-1",
                event_type: "approval.started",
                destination: "webhook://approval",
                status: "failed",
                attempts: 2,
                created_at: "2026-03-24T10:00:00Z",
              },
            ],
          },
        });
      }
      if (url === "/admin/outbox/events") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "event-1",
                event_type: "approval.completed",
                status: "poisoned",
                attempts: 3,
                created_at: "2026-03-24T10:01:00Z",
              },
            ],
          },
        });
      }
      throw new Error(`Unexpected GET ${url}`);
    });

    postMock.mockResolvedValue({ data: {} });

    render(
      <MemoryRouter>
        <ApprovalsOutboxPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/доставки согласований/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith("/admin/outbox/delivery-1/retry");
    });

    fireEvent.click(screen.getByRole("button", { name: /requeue/i }));
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith("/admin/outbox/events/event-1/requeue");
    });
  });

  it("shows error state when load fails", async () => {
    getMock.mockRejectedValue({ status: 500, message: "outbox load failed" });

    render(
      <MemoryRouter>
        <ApprovalsOutboxPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("outbox load failed");
    });
  });
});
