import { render, screen, waitFor } from "@testing-library/react";

import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import BriefingsPage from "@/pages/briefings/BriefingsPage";
import { useAuthStore } from "@/stores/auth";

const listTemplatesMock = vi.fn();
const listJournalsMock = vi.fn();
const listEntriesMock = vi.fn();
const listOverdueMock = vi.fn();
const remindOverdueMock = vi.fn();
const createEntryMock = vi.fn();
const fetchAllPersonsMock = vi.fn();

vi.mock("@/api/briefings", () => ({
  briefingsApi: {
    listTemplates: () => listTemplatesMock(),
    listJournals: () => listJournalsMock(),
    listEntries: () => listEntriesMock(),
    listOverdue: () => listOverdueMock(),
    remindOverdue: () => remindOverdueMock(),
    createTemplate: vi.fn(),
    createJournal: vi.fn(),
    createEntry: (...a: unknown[]) => createEntryMock(...a),
    sign: vi.fn(),
    complete: vi.fn(),
  },
}));

vi.mock("@/api/personsApi", () => ({
  fetchAllPersons: () => fetchAllPersonsMock(),
}));

describe("BriefingsPage", () => {
  beforeEach(() => {
    listTemplatesMock.mockReset();
    listJournalsMock.mockReset();
    listEntriesMock.mockReset();
    listOverdueMock.mockReset();
    remindOverdueMock.mockReset();

    createEntryMock.mockReset();
    fetchAllPersonsMock.mockReset();

    listTemplatesMock.mockResolvedValue([]);
    listJournalsMock.mockResolvedValue([]);
    listEntriesMock.mockResolvedValue([]);
    listOverdueMock.mockResolvedValue([]);
    remindOverdueMock.mockResolvedValue({ count: 1 });
    createEntryMock.mockResolvedValue({});
    fetchAllPersonsMock.mockResolvedValue([]);

    useAuthStore.setState({
      user: {
        id: "briefings-user",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "briefings@example.com",
        full_name: "Briefings User",
        roles: ["worker"],
        permissions: [PERMISSIONS.TRAINING_VIEW],
        attributes: { tenant_id: "tenant-1" },
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });
  });

  it("disables briefing management actions without assign permission", async () => {
    render(
      <MemoryRouter>
        <BriefingsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(listTemplatesMock).toHaveBeenCalled();
    });

    expect(
      screen.getByRole("button", { name: "Напомнить о просрочке" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Создать шаблон" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Создать журнал" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Назначить" })).toBeDisabled();
  });

  it("enables management actions and allows reminders with assign permission", async () => {
    useAuthStore.setState((state) => ({
      ...state,
      user: state.user
        ? {
            ...state.user,
            permissions: [
              PERMISSIONS.TRAINING_VIEW,
              PERMISSIONS.TRAINING_ASSIGN,
            ],
          }
        : null,
    }));

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <BriefingsPage />
      </MemoryRouter>,
    );

    const remindButton = await screen.findByRole("button", {
      name: "Напомнить о просрочке",
    });
    expect(remindButton).toBeEnabled();

    await user.click(remindButton);
    expect(remindOverdueMock).toHaveBeenCalled();
  });

  it("назначает инструктаж выбранному сотруднику (person_id из persons, не company-id)", async () => {
    useAuthStore.setState((state) => ({
      ...state,
      user: state.user
        ? {
            ...state.user,
            permissions: [
              PERMISSIONS.TRAINING_VIEW,
              PERMISSIONS.TRAINING_ASSIGN,
            ],
          }
        : null,
    }));
    fetchAllPersonsMock.mockResolvedValue([
      {
        id: "person-1",
        full_name: "Иванов Иван Иванович",
        first_name: "Иван",
        last_name: "Иванов",
        status: "active",
      },
    ]);

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <BriefingsPage />
      </MemoryRouter>,
    );

    // Label и <select> рендерятся безусловно, а опции строятся из ответа
    // fetchAllPersons — ждём саму опцию из мока, selectOptions не ретраит.
    await screen.findByRole("option", { name: "Иванов Иван Иванович" });
    const personSelect = screen.getByLabelText("Сотрудник");
    await user.selectOptions(personSelect, "person-1");
    await user.click(screen.getByRole("button", { name: "Назначить" }));

    await waitFor(() => expect(createEntryMock).toHaveBeenCalled());
    expect(createEntryMock.mock.calls[0][0]).toMatchObject({
      person_id: "person-1",
    });
  });

  it("экран укладывается в UX-бюджет (разд. 59.2)", async () => {
    // Существующий, насыщенный экран: четыре действия и таблица. Проверка
    // ставится не только на новые экраны — иначе она зелёная по построению.
    const { container } = render(
      <MemoryRouter>
        <BriefingsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(listTemplatesMock).toHaveBeenCalled();
    });

    // Экран сегодня НЕ укладывается: три главных действия и одиннадцать полей.
    // Это записано явным долгом (`uxBudgetDebt.ts`) — ТЗ разд. 59.2 допускает
    // превышение «только с явным обоснованием и пометкой». Проверка стережёт
    // обе стороны: экран не должен стать хуже, а починив его, обязаны снять
    // запись — иначе список долгов перестанет отражать правду.
    const delta = uxBudgetDelta(container, "BriefingsPage");
    expect(delta.unexpected).toEqual([]);
    expect(delta.stale).toEqual([]);
  });
});
