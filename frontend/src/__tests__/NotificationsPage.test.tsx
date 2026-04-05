import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import NotificationsPage from "@/pages/notifications/NotificationsPage";

const getMock = vi.fn();
const postMock = vi.fn();
const putMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    put: (...args: unknown[]) => putMock(...args),
  }
}));

describe("NotificationsPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    putMock.mockReset();
  });

  it("marks selected unread notifications as read", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/notifications/settings/me") {
        return Promise.resolve({ data: { email_enabled: true, telegram_enabled: false, inapp_enabled: true, digest_mode: "daily" } });
      }
      return Promise.resolve({
        data: {
          unread_count: 1,
          items: [
            { id: "n1", title: "Approval due", body: "Approve document", type: "ApprovalDeadline", status: "queued", channel: "inapp", priority: "critical", is_read: false, deeplink: "/workflow/1" },
            { id: "n2", title: "Package ready", body: "Open package", type: "PackageRunCompleted", status: "read", channel: "email", priority: "high", is_read: true, deeplink: "/pack-runs/2" }
          ]
        }
      });
    });
    postMock.mockResolvedValue({ data: { updated: 1 } });
    putMock.mockResolvedValue({ data: {} });

    render(
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Approval due")).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Выбрать уведомление n1"));
    await user.click(screen.getByRole("button", { name: /отметить выбранные/i }));

    await waitFor(() => expect(postMock).toHaveBeenCalledWith("/notifications/mark-read", { ids: ["n1"] }));
    const links = screen.getAllByRole("link", { name: /открыть связанную сущность/i });
    expect(links[0]).toHaveAttribute("href", "/workflow/1");
  });

  it("shows action error and keeps notifications list visible when mark-read fails", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/notifications/settings/me") {
        return Promise.resolve({ data: { email_enabled: true, telegram_enabled: false, inapp_enabled: true, digest_mode: "daily" } });
      }
      if (url === "/notifications/templates") {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({
        data: {
          unread_count: 1,
          items: [
            { id: "n1", title: "Approval due", body: "Approve document", type: "ApprovalDeadline", status: "queued", channel: "inapp", priority: "critical", is_read: false, deeplink: "/workflow/1" },
          ]
        }
      });
    });
    postMock.mockRejectedValueOnce({ status: 400, message: "mark read failed" });

    render(
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Approval due")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /отметить все прочитанными/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("mark read failed");
    });
    expect(screen.getByText("Approval due")).toBeInTheDocument();
  });

  it("shows action error and keeps edited settings when save fails", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/notifications/settings/me") {
        return Promise.resolve({ data: { email_enabled: true, telegram_enabled: false, inapp_enabled: true, digest_mode: "daily", email: "ops@test.local" } });
      }
      if (url === "/notifications/templates") {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({ data: { unread_count: 0, items: [] } });
    });
    putMock.mockRejectedValueOnce({ status: 400, message: "settings save failed" });

    render(
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>
    );

    const digestInput = await screen.findByPlaceholderText("Режим дайджеста: off / daily / weekly");
    fireEvent.change(digestInput, { target: { value: "weekly" } });
    fireEvent.click(screen.getByRole("button", { name: /сохранить настройки/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("settings save failed");
    });
    expect(screen.getByPlaceholderText("Режим дайджеста: off / daily / weekly")).toHaveValue("weekly");
  });
});
