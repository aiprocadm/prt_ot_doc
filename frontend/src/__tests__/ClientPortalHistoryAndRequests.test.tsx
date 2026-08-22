import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { uxBudgetDelta } from "@/test-utils/uxBudget";

const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: getMock,
  },
}));

import ClientPortalHistoryPage from "@/pages/client-portal/ClientPortalHistoryPage";
import ClientPortalRequestsPage from "@/pages/client-portal/ClientPortalRequestsPage";
import PortalRequestsPage from "@/pages/portal-requests/PortalRequestsPage";

const setupApi = () => {
  getMock.mockImplementation((url: string) => {
    if (url === "/portal-requests") {
      // Дашборд заявок портала: плоские KPI-числа, как отдаёт бэкенд.
      return Promise.resolve({
        data: {
          total_requests: 4,
          open_requests: 2,
          overdue_requests: 1,
        },
      });
    }
    if (url === "/client-portal/packages") {
      return Promise.resolve({
        data: [
          {
            id: "run-1",
            status: "published",
            started_at: "2026-03-18T10:00:00Z",
          },
        ],
      });
    }
    return Promise.resolve({
      data: {
        run: { id: "run-1", status: "published" },
        history: {
          status_flow: ["running", "published"],
          events_count: 2,
          tickets_count: 1,
          requirements_total: 3,
          requirements_missing: 1,
        },
        files: [],
        events: [
          {
            id: "evt-1",
            type: "package_run.published",
            created_at: "2026-03-18T11:00:00Z",
          },
        ],
        tickets: [
          {
            id: "ticket-1",
            title: "Нужна уточняющая справка",
            status: "open",
            created_at: "2026-03-18T12:00:00Z",
          },
        ],
      },
    });
  });
};

describe("client portal pages", () => {
  it("renders history from package details API", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <ClientPortalHistoryPage />
      </MemoryRouter>,
    );

    // Ждём само событие из API: заголовок «События пакета» статичен и
    // появляется ДО загрузки деталей — синхронный getBy* давал гонку.
    expect(
      await screen.findByText(/package_run.published/i),
    ).toBeInTheDocument();
    expect(screen.getByText("События пакета")).toBeInTheDocument();
  });

  it("renders requests from package details API", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <ClientPortalRequestsPage />
      </MemoryRouter>,
    );

    // Ждём сам текст из API: заголовок статичен и появляется до загрузки —
    // синхронная проверка сразу после него гонялась на медленном CI.
    expect(
      await screen.findByText(/Нужна уточняющая справка/i),
    ).toBeInTheDocument();
  });

  // BIZ-60 волна 5: приёмка UX-бюджета. Меряем НАПОЛНЕННЫЙ экран — после
  // ожидания данных из мока, иначе замер видит пустой каркас и врёт «в бюджете».
  it("ClientPortalHistoryPage в UX-бюджете (BIZ-60)", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <ClientPortalHistoryPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText(/package_run.published/i),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "ClientPortalHistoryPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("ClientPortalRequestsPage в UX-бюджете (BIZ-60)", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <ClientPortalRequestsPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText(/Нужна уточняющая справка/i),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "ClientPortalRequestsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("PortalRequestsPage в UX-бюджете (BIZ-60)", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <PortalRequestsPage />
      </MemoryRouter>,
    );
    // Ждём KPI-карточку из данных мока: заголовок собирается из ключа ответа.
    expect(await screen.findByText("Total Requests")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "PortalRequestsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
