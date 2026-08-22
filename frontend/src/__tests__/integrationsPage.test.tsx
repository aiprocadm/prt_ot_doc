import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import IntegrationsPage from "@/pages/integrations/IntegrationsPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

describe("IntegrationsPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    vi.mocked(toast.error).mockReset();
    useAuthStore.setState({
      user: {
        id: "user-1",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "user@example.com",
        full_name: "User",
        roles: ["admin"],
        permissions: [PERMISSIONS.ADMIN_OUTBOX_MANAGE],
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });
  });

  it("shows toast when delivery retry fails", async () => {
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
                updated_at: "2026-03-24T10:01:00Z",
              },
            ],
          },
        });
      }
      if (url === "/admin/outbox/events") {
        return Promise.resolve({ data: { items: [] } });
      }
      if (url === "/integrations/readiness") {
        return Promise.resolve({
          data: {
            providers: [],
            webhooks: {
              configured_total: 0,
              enabled_total: 0,
              delivery_failed_total: 1,
            },
          },
        });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
    postMock.mockRejectedValue({ message: "retry failed" });

    render(<IntegrationsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /повторить/i }));

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith("/admin/outbox/delivery-1/retry");
    });
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("retry failed");
      expect(screen.getByRole("button", { name: /повторить/i })).toBeEnabled();
    });
  });

  it("shows toast when event requeue fails", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/admin/outbox") {
        return Promise.resolve({ data: { items: [] } });
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
                next_attempt_at: null,
              },
            ],
          },
        });
      }
      if (url === "/integrations/readiness") {
        return Promise.resolve({
          data: {
            providers: [],
            webhooks: {
              configured_total: 0,
              enabled_total: 0,
              delivery_failed_total: 0,
            },
          },
        });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
    postMock.mockRejectedValue({ message: "requeue failed" });

    render(<IntegrationsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /в очередь/i }));

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        "/admin/outbox/events/event-1/requeue",
      );
    });
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("requeue failed");
      expect(screen.getByRole("button", { name: /в очередь/i })).toBeEnabled();
    });
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
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
                updated_at: "2026-03-24T10:01:00Z",
              },
              {
                id: "delivery-2",
                event_type: "approval.completed",
                destination: "webhook://approval",
                status: "sent",
                attempts: 1,
                created_at: "2026-03-24T10:02:00Z",
                updated_at: "2026-03-24T10:03:00Z",
                sent_at: "2026-03-24T10:03:00Z",
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
                next_attempt_at: null,
              },
            ],
          },
        });
      }
      if (url === "/integrations/readiness") {
        return Promise.resolve({
          data: {
            providers: [
              {
                provider: "diadoc",
                health_status: "ready",
                configured: true,
                adapter: "diadoc-http",
                reachable: true,
              },
            ],
            webhooks: {
              configured_total: 2,
              enabled_total: 1,
              delivery_failed_total: 1,
            },
          },
        });
      }
      throw new Error(`Unexpected GET ${url}`);
    });

    render(<IntegrationsPage />);

    await screen.findByText("diadoc");
    await screen.findByRole("button", { name: /повторить/i });
    await screen.findByRole("button", { name: /в очередь/i });

    const budget = uxBudgetDelta(document.body, "IntegrationsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
