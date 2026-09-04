import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => apiClientMock.get(...args),
  },
}));

import AuditPage from "@/pages/audit/AuditPage";
import { useAuditStore } from "@/stores/audit";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import type { AuditLogDto } from "@/types/dto/audit";

const auditItems: AuditLogDto[] = [
  {
    id: "log-1",
    created_at: "2026-08-20T10:15:00Z",
    updated_at: "2026-08-20T10:15:00Z",
    actor: {
      id: "user-1",
      email: "ivanov@example.com",
      full_name: "Иванов Иван",
    },
    action: "document.sign",
    entity_type: "document",
    entity_id: "doc-1",
  },
  {
    id: "log-2",
    created_at: "2026-08-20T11:30:00Z",
    updated_at: "2026-08-20T11:30:00Z",
    actor: {
      id: "user-2",
      email: "petrova@example.com",
      full_name: "Петрова Анна",
    },
    action: "user.login",
    entity_type: "user",
    entity_id: "user-2",
  },
  {
    id: "log-3",
    created_at: "2026-08-21T09:05:00Z",
    updated_at: "2026-08-21T09:05:00Z",
    actor: {
      id: "user-1",
      email: "ivanov@example.com",
      full_name: "Иванов Иван",
    },
    action: "briefing.assign",
    entity_type: "briefing",
    entity_id: "brief-7",
  },
];

const renderPage = async () => {
  await act(async () => {
    render(
      <MemoryRouter>
        <AuditPage />
      </MemoryRouter>,
    );
  });
};

describe("AuditPage", () => {
  beforeEach(() => {
    apiClientMock.get.mockReset();
    // Стор — модульный синглтон: без сброса состояние утекает между тестами.
    useAuditStore.getState().reset();
    apiClientMock.get.mockImplementation((url: string) => {
      if (url !== "/audit") throw new Error(`Unexpected GET ${url}`);
      return Promise.resolve({
        data: {
          items: auditItems,
          pagination: { page: 1, page_size: 10, total: auditItems.length },
        },
      });
    });
  });

  it("экран в UX-бюджете на наполненном журнале (BIZ-60)", async () => {
    // Меряем экран с непустым журналом: колонки таблицы и пагинация
    // существуют только при данных — замер пустого состояния соврал бы.
    await renderPage();
    expect(await screen.findByText("Петрова Анна")).toBeInTheDocument();
    expect(screen.getAllByText("Иванов Иван").length).toBeGreaterThan(0);

    const budget = uxBudgetDelta(document.body, "AuditPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("применяет фильтр поиска и перезапрашивает журнал", async () => {
    const user = userEvent.setup();
    await renderPage();
    expect(await screen.findByText("Петрова Анна")).toBeInTheDocument();

    await act(async () => {
      await user.type(screen.getByLabelText("Поиск"), "document");
      await user.click(screen.getByRole("button", { name: "Применить" }));
    });

    expect(apiClientMock.get).toHaveBeenLastCalledWith("/audit", {
      params: expect.objectContaining({ search: "document" }),
    });
  });
});
