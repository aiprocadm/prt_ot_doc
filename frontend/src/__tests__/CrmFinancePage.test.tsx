import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const { getSnapshotMock, listCompaniesMock } = vi.hoisted(() => ({
  getSnapshotMock: vi.fn(),
  listCompaniesMock: vi.fn(),
}));

vi.mock("@/api/crmFinance", () => ({
  crmFinanceApi: {
    getSnapshot: getSnapshotMock,
  },
}));

vi.mock("@/stores/companies", () => ({
  useCompaniesStore: () => ({
    items: [{ id: "company-1", name: "АО ТехПром" }],
    list: listCompaniesMock,
  }),
}));

import CrmFinancePage from "@/pages/crm-finance/CrmFinancePage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

describe("CrmFinancePage", () => {
  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    // BIZ-60 волна 3. Замер НАПОЛНЕННОГО состояния (урок NotificationsPage):
    // моки в этом файле объявляются per-test, поэтому тест бюджета несёт
    // свои. Волна нашла здесь восьмую колонку — она объединена со счётчиком
    // заказов («Счета / заказы»), и приёмка стережёт, чтобы не вернулась.
    getSnapshotMock.mockResolvedValue({
      contracts: [
        {
          id: "contract-1",
          company_id: "company-1",
          title: "Пакет Ростехнадзор",
          counterparty_name: "АО ТехПром",
          contract_number: "DL-101",
          status: "active",
          total_amount: 1480000,
          currency: "RUB",
          valid_until: "2026-12-31",
        },
      ],
      orders: [
        {
          id: "order-1",
          contract_id: "contract-1",
          order_number: "ORD-10",
          status: "approved",
          total_amount: 1480000,
          currency: "RUB",
        },
      ],
      invoices: [
        {
          id: "invoice-1",
          contract_id: "contract-1",
          order_id: "order-1",
          invoice_number: "INV-1",
          status: "paid",
          total_amount: 1480000,
          currency: "RUB",
          due_at: "2026-04-01",
          paid_at: "2026-03-20",
        },
      ],
      billing: {
        subscription_status: "active",
        plan: { code: "pro", name: "Pro" },
      },
    });
    listCompaniesMock.mockResolvedValue(undefined);

    render(
      <MemoryRouter>
        <CrmFinancePage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("АО ТехПром")).toBeInTheDocument();
    });

    const budget = uxBudgetDelta(document.body, "CrmFinancePage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("renders real contract-based finance rows after loading", async () => {
    getSnapshotMock.mockResolvedValue({
      contracts: [
        {
          id: "contract-1",
          company_id: "company-1",
          title: "Пакет Ростехнадзор",
          counterparty_name: "АО ТехПром",
          contract_number: "DL-101",
          status: "active",
          total_amount: 1480000,
          currency: "RUB",
          valid_until: "2026-12-31",
        },
      ],
      orders: [
        {
          id: "order-1",
          contract_id: "contract-1",
          order_number: "ORD-10",
          status: "approved",
          total_amount: 1480000,
          currency: "RUB",
        },
      ],
      invoices: [
        {
          id: "invoice-1",
          contract_id: "contract-1",
          order_id: "order-1",
          invoice_number: "INV-1",
          status: "paid",
          total_amount: 1480000,
          currency: "RUB",
          due_at: "2026-04-01",
          paid_at: "2026-03-20",
        },
      ],
      billing: {
        subscription_status: "active",
        plan: { code: "pro", name: "Pro" },
      },
    });
    listCompaniesMock.mockResolvedValue(undefined);

    render(
      <MemoryRouter>
        <CrmFinancePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("АО ТехПром")).toBeInTheDocument();
    });
    expect(screen.getByText("Пакет Ростехнадзор")).toBeInTheDocument();
    expect(screen.getByText(/план: pro/i)).toBeInTheDocument();
    expect(screen.getByText("DL-101")).toBeInTheDocument();
  });

  it("shows empty state when no finance data exists", async () => {
    getSnapshotMock.mockResolvedValue({
      contracts: [],
      orders: [],
      invoices: [],
      billing: null,
    });
    listCompaniesMock.mockResolvedValue(undefined);

    render(
      <MemoryRouter>
        <CrmFinancePage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/сделки не найдены/i)).toBeInTheDocument();
    });
  });

  it("filters rows by query", async () => {
    getSnapshotMock.mockResolvedValue({
      contracts: [
        {
          id: "contract-1",
          company_id: "company-1",
          title: "Пакет Ростехнадзор",
          counterparty_name: "АО ТехПром",
          contract_number: "DL-101",
          status: "active",
          total_amount: 1480000,
          currency: "RUB",
          valid_until: null,
        },
        {
          id: "contract-2",
          company_id: "company-1",
          title: "Пакет Экология",
          counterparty_name: "АО ТехПром",
          contract_number: "DL-102",
          status: "draft",
          total_amount: 640000,
          currency: "RUB",
          valid_until: null,
        },
      ],
      orders: [],
      invoices: [],
      billing: null,
    });
    listCompaniesMock.mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <CrmFinancePage />
      </MemoryRouter>,
    );

    await screen.findByText("Пакет Ростехнадзор");
    await user.type(
      screen.getByPlaceholderText(/поиск по договору/i),
      "Экология",
    );

    expect(screen.getByText("Пакет Экология")).toBeInTheDocument();
    expect(screen.queryByText("Пакет Ростехнадзор")).not.toBeInTheDocument();
  });
});
