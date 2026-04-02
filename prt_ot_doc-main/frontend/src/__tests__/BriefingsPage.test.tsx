import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import BriefingsPage from "@/pages/briefings/BriefingsPage";
import { useAuthStore } from "@/stores/auth";

const listTemplatesMock = vi.fn();
const listJournalsMock = vi.fn();
const listEntriesMock = vi.fn();
const listOverdueMock = vi.fn();
const remindOverdueMock = vi.fn();

vi.mock("@/api/briefings", () => ({
  briefingsApi: {
    listTemplates: () => listTemplatesMock(),
    listJournals: () => listJournalsMock(),
    listEntries: () => listEntriesMock(),
    listOverdue: () => listOverdueMock(),
    remindOverdue: () => remindOverdueMock(),
    createTemplate: vi.fn(),
    createJournal: vi.fn(),
    createEntry: vi.fn(),
    sign: vi.fn(),
    complete: vi.fn()
  }
}));

vi.mock("@/stores/companies", () => ({
  useCompaniesStore: () => ({
    items: [],
    list: vi.fn().mockResolvedValue(undefined)
  })
}));

describe("BriefingsPage", () => {
  beforeEach(() => {
    listTemplatesMock.mockReset();
    listJournalsMock.mockReset();
    listEntriesMock.mockReset();
    listOverdueMock.mockReset();
    remindOverdueMock.mockReset();

    listTemplatesMock.mockResolvedValue([]);
    listJournalsMock.mockResolvedValue([]);
    listEntriesMock.mockResolvedValue([]);
    listOverdueMock.mockResolvedValue([]);
    remindOverdueMock.mockResolvedValue({ count: 1 });

    useAuthStore.setState({
      user: {
        id: "briefings-user",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "briefings@example.com",
        full_name: "Briefings User",
        roles: ["worker"],
        permissions: [PERMISSIONS.TRAINING_VIEW],
        attributes: { tenant_id: "tenant-1" }
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });
  });

  it("disables briefing management actions without assign permission", async () => {
    render(
      <MemoryRouter>
        <BriefingsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(listTemplatesMock).toHaveBeenCalled();
    });

    expect(screen.getByRole("button", { name: "Напомнить о просрочке" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Создать шаблон" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Создать журнал" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Назначить" })).toBeDisabled();
  });

  it("enables management actions and allows reminders with assign permission", async () => {
    useAuthStore.setState((state) => ({
      ...state,
      user: state.user
        ? {
            ...state.user,
            permissions: [PERMISSIONS.TRAINING_VIEW, PERMISSIONS.TRAINING_ASSIGN]
          }
        : null
    }));

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <BriefingsPage />
      </MemoryRouter>
    );

    const remindButton = await screen.findByRole("button", { name: "Напомнить о просрочке" });
    expect(remindButton).toBeEnabled();

    await user.click(remindButton);
    expect(remindOverdueMock).toHaveBeenCalled();
  });
});
