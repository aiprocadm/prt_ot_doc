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

import ClientPortalDashboardPage from "@/pages/client-portal/ClientPortalDashboardPage";
import ClientPortalDocumentsPage from "@/pages/client-portal/ClientPortalDocumentsPage";

// Оба экрана ходят через useClientPortalPackages: сперва список пакетов,
// затем детали первого (хук выбирает его сам). Мокаем оба ответа с данными,
// чтобы мерить НАПОЛНЕННЫЙ экран, а не пустой каркас.
const setupApi = () => {
  getMock.mockImplementation((url: string) => {
    if (url === "/client-portal/packages") {
      return Promise.resolve({
        data: [
          {
            id: "run-1",
            package_id: "pkg-1",
            status: "published",
            started_at: "2026-03-18T10:00:00Z",
          },
        ],
      });
    }
    // /client-portal/packages/pkg-1 — детали выбранного пакета.
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
        files: [
          {
            kind: "report_pdf",
            sha256: "abc123def456",
            size: 2048,
            signed_url: "https://files.example.test/report.pdf",
          },
        ],
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

describe("client portal dashboard and documents pages", () => {
  it("renders dashboard summary from packages API", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <ClientPortalDashboardPage />
      </MemoryRouter>,
    );

    // Ждём строку списка из API: заголовки карточек статичны и появляются
    // ДО загрузки — синхронный getBy* давал бы гонку.
    expect(await screen.findByText("run-1")).toBeInTheDocument();
    expect(screen.getByText("Открытые требования")).toBeInTheDocument();
  });

  it("renders documents with package artefacts from details API", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <ClientPortalDocumentsPage />
      </MemoryRouter>,
    );

    // Ждём артефакт из деталей пакета — он появляется последним.
    expect(await screen.findByText("report_pdf")).toBeInTheDocument();
    expect(screen.getByText("pkg-1")).toBeInTheDocument();
    expect(screen.getByText("Скачать файл")).toBeInTheDocument();
  });

  // BIZ-60 волна 5: приёмка UX-бюджета. Меряем НАПОЛНЕННЫЙ экран — после
  // ожидания данных из мока, иначе замер видит пустой каркас и врёт «в бюджете».
  it("ClientPortalDashboardPage в UX-бюджете (BIZ-60)", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <ClientPortalDashboardPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("run-1")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "ClientPortalDashboardPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("ClientPortalDocumentsPage в UX-бюджете (BIZ-60)", async () => {
    setupApi();
    render(
      <MemoryRouter>
        <ClientPortalDocumentsPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("report_pdf")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "ClientPortalDocumentsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
