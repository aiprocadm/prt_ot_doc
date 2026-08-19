import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ClientAuditReportPage,
  ManagedClient,
} from "@/api/managedClients";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  auditReports: vi.fn(),
  runAudit: vi.fn(),
  update: vi.fn(),
  sendReport: vi.fn(),
}));

vi.mock("@/api/managedClients", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  managedClientsApi: api,
}));

import ClientCardPage from "@/pages/managed-clients/ClientCardPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const CLIENT: ManagedClient = {
  id: "mc1",
  name: "ООО Ромашка",
  mode: "lightweight",
  company_id: "comp-a",
  dedicated_tenant_slug: null,
  contract_status: "active",
  contract_no: "Д-1",
  contract_starts_at: null,
  contract_ends_at: "2026-12-31",
  responsible_person_id: null,
  notes: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const REPORTS: ClientAuditReportPage = {
  items: [
    {
      id: "r2",
      period_start: "2026-08-11",
      period_end: "2026-08-18",
      overall: "red",
      summary:
        "Изменений за период: 1 (Принят новый сотрудник — 1). Просрочено и не оформлено — Медосмотры: Разрывы с эталоном — не оформлено вовсе: 2. Что нужно сделать: Медосмотры: Разрывы с эталоном — не оформлено вовсе: 2.",
      payload: {},
    },
    {
      id: "r1",
      period_start: "2026-08-04",
      period_end: "2026-08-11",
      overall: "green",
      summary: "Разрывов с эталоном не найдено.",
      payload: {},
    },
  ],
  total: 2,
};

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/managed-clients/mc1"]}>
      <Routes>
        <Route
          path="/managed-clients/:clientId"
          element={<ClientCardPage />}
        />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.get.mockResolvedValue(CLIENT);
  api.auditReports.mockResolvedValue(REPORTS);
  api.update.mockResolvedValue(CLIENT);
  api.sendReport.mockResolvedValue({
    status: "no_consent",
    reason: "Клиент не давал согласия на получение отчётов — включите его в карточке",
    recipient: "client@example.com",
  });
  api.runAudit.mockResolvedValue({
    created: 1,
    already_current: 0,
    skipped_dedicated: 1,
    summary: "Создано отчётов: 1, пропущено (свой контур): 1",
  });
});

describe("ClientCardPage (BIZ-51 срез-10)", () => {
  it("показывает клиента и отчёты с итогом словом и текстом целиком", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getAllByTestId("audit-report-row").length).toBe(2),
    );

    expect(api.get).toHaveBeenCalledWith("mc1");
    expect(api.auditReports).toHaveBeenCalledWith("mc1");
    expect(screen.getByTestId("client-info")).toHaveTextContent("Действует");
    const rows = screen.getAllByTestId("audit-report-row");
    // Итог — словом, не только цветом; текст отчёта виден целиком.
    expect(within(rows[0]).getByText("Разрывы")).toBeInTheDocument();
    expect(
      within(rows[0]).getByText(/Что нужно сделать: Медосмотры/),
    ).toBeInTheDocument();
    expect(within(rows[1]).getByText("В порядке")).toBeInTheDocument();
  });

  it("кнопка «Собрать отчёт сейчас» зовёт сервер, итог остаётся на экране", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getAllByTestId("audit-report-row").length).toBe(2),
    );
    api.auditReports.mockClear();

    await userEvent.click(screen.getByTestId("run-audit-button"));

    await waitFor(() =>
      expect(screen.getByTestId("run-audit-result")).toHaveTextContent(
        "пропущено (свой контур): 1",
      ),
    );
    // Список перечитан — свежий отчёт виден без F5.
    await waitFor(() => expect(api.auditReports).toHaveBeenCalled());
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getAllByTestId("audit-report-row").length).toBe(2),
    );

    const budget = uxBudgetDelta(document.body, "ClientCardPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("без отчётов объясняет, откуда они возьмутся", async () => {
    api.auditReports.mockResolvedValue({ items: [], total: 0 });
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Отчётов пока нет")).toBeInTheDocument(),
    );
    expect(screen.getByText(/еженедельно/)).toBeInTheDocument();
  });

  it("выключенный модуль объяснён, а не выглядит ошибкой", async () => {
    api.get.mockRejectedValue({
      status: 404,
      code: "MANAGED_CLIENTS_DISABLED",
      message: "disabled",
    });
    api.auditReports.mockRejectedValue({
      status: 404,
      code: "MANAGED_CLIENTS_DISABLED",
      message: "disabled",
    });
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Модуль не подключён")).toBeInTheDocument(),
    );
  });
});

describe("Отчёт клиенту (BIZ-51 срез-11)", () => {
  it("показывает, что адрес не указан, пока его не задали", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("report-email-state")).toBeInTheDocument(),
    );

    expect(screen.getByTestId("report-email-state")).toHaveTextContent(
      "адрес не указан",
    );
    // Форма скрыта до клика — бюджет экрана (BIZ-60).
    expect(screen.queryByTestId("report-email-form")).not.toBeInTheDocument();
  });

  it("сохраняет адрес и согласие", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("edit-report-email")).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByTestId("edit-report-email"));
    await userEvent.type(
      screen.getByLabelText("Адрес клиента для отчётов"),
      "client@example.com",
    );
    await userEvent.click(screen.getByTestId("report-opt-in"));
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith("mc1", {
        report_email: "client@example.com",
        report_opt_in: true,
      }),
    );
  });

  it("причина отказа отправки остаётся на экране", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getAllByTestId("send-report").length).toBeGreaterThan(0),
    );

    await userEvent.click(screen.getAllByTestId("send-report")[0]);

    await waitFor(() =>
      expect(screen.getByTestId("send-report-result")).toHaveTextContent(
        "согласия",
      ),
    );
    expect(api.sendReport).toHaveBeenCalledWith("mc1", "r2");
  });
});
