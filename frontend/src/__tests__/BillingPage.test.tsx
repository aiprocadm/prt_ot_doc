import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BillingPage from "@/pages/admin/BillingPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getBillingSummaryMock = vi.fn();
const getBillingInvoicesMock = vi.fn();
const getBillingPlansMock = vi.fn();
const getBillingEditionsMock = vi.fn();
const changeBillingPlanMock = vi.fn();
const markSubscriptionPastDueMock = vi.fn();
const markSubscriptionPaidMock = vi.fn();
const suspendSubscriptionMock = vi.fn();
const activateSubscriptionMock = vi.fn();

vi.mock("@/api/billing", () => ({
  getBillingSummary: (...args: unknown[]) => getBillingSummaryMock(...args),
  getBillingInvoices: (...args: unknown[]) => getBillingInvoicesMock(...args),
  getBillingPlans: (...args: unknown[]) => getBillingPlansMock(...args),
  getBillingEditions: (...args: unknown[]) => getBillingEditionsMock(...args),
  changeBillingPlan: (...args: unknown[]) => changeBillingPlanMock(...args),
  markSubscriptionPastDue: (...args: unknown[]) =>
    markSubscriptionPastDueMock(...args),
  markSubscriptionPaid: (...args: unknown[]) =>
    markSubscriptionPaidMock(...args),
  suspendSubscription: (...args: unknown[]) => suspendSubscriptionMock(...args),
  activateSubscription: (...args: unknown[]) =>
    activateSubscriptionMock(...args),
}));

describe("BillingPage", () => {
  beforeEach(() => {
    getBillingSummaryMock.mockReset();
    getBillingInvoicesMock.mockReset();
    getBillingPlansMock.mockReset();
    getBillingEditionsMock.mockReset();
    changeBillingPlanMock.mockReset();
    markSubscriptionPastDueMock.mockReset();
    markSubscriptionPaidMock.mockReset();
    suspendSubscriptionMock.mockReset();
    activateSubscriptionMock.mockReset();

    getBillingSummaryMock.mockResolvedValue({
      plan: { code: "basic", name: "Basic" },
      subscription: {
        status: "active",
        period_start: "2026-03-01",
        period_end: "2026-03-31",
        grace_until: null,
        auto_renew: true,
      },
      limits: {
        max_generations_per_month: 100,
        edo_outgoing_per_month: 50,
        max_s3_bytes: 1000,
        max_integrations: 5,
      },
      features: {},
      usage: { docs_generated: 10, edo_outgoing: 5, s3_bytes_used: 100 },
      remaining: {},
    });
    getBillingInvoicesMock.mockResolvedValue([]);
    getBillingPlansMock.mockResolvedValue([
      { code: "basic", name: "Basic", limits: {}, features: {} },
      { code: "pro", name: "Pro", limits: {}, features: {} },
    ]);
    // BIZ-53 срез-2: редакции — продуктовая упаковка тарифов. В наборе
    // намеренно есть ДВЕ редакции на одном тарифе: так проверяется, что экран
    // показывает обе и не выдаёт их за один вариант.
    getBillingEditionsMock.mockResolvedValue([
      {
        code: "start_ot",
        title: "Start OT",
        audience: "Микро и малый бизнес: одно юрлицо, примерно до 50 человек",
        plan_code: "basic",
        includes: "Документы, инструктажи, карточки СИЗ",
        beyond_modules: "",
      },
      {
        code: "safety_suite",
        title: "Safety Suite",
        audience: "Крупный и многопрофильный бизнес",
        plan_code: "pro",
        includes: "Полный контур",
        beyond_modules: "",
      },
      {
        code: "enterprise_holding",
        title: "Enterprise Holding",
        audience: "Холдинг с филиалами",
        plan_code: "pro",
        includes: "Всё из Safety Suite.",
        beyond_modules: "SSO и LDAP, on-prem, выделенный SLA",
      },
    ]);
  });

  it("shows action error and keeps plan cards visible when plan change fails", async () => {
    changeBillingPlanMock.mockRejectedValueOnce({
      status: 400,
      message: "plan change failed",
    });

    render(
      <MemoryRouter>
        <BillingPage />
      </MemoryRouter>,
    );

    // Кнопки «Сменить» появляются только после ответа getBillingPlans —
    // заголовок «Тариф и статус» статичен, синхронный getAllByRole давал гонку.
    const switchPlanButtons = await screen.findAllByText("Сменить");
    expect(switchPlanButtons.length).toBeGreaterThanOrEqual(1);
    fireEvent.click(switchPlanButtons[0]!.closest("button") as HTMLElement);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("plan change failed");
    });
    expect(screen.getByText("Тарифы")).toBeInTheDocument();
    // BIZ-53 срез-2: у тарифа показывается РЕДАКЦИЯ, а не техническое имя.
    // Обе редакции одного тарифа названы — иначе вторая была бы невидимой.
    expect(
      screen.getByText("Safety Suite · Enterprise Holding"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Холдинг с филиалами/)).toBeInTheDocument();
    // Отличие «сверх модулей» видно на экране: без него две редакции на одном
    // тарифе выглядели бы двумя именами одного и того же.
    expect(screen.getByText(/выделенный SLA/)).toBeInTheDocument();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    render(
      <MemoryRouter>
        <BillingPage />
      </MemoryRouter>,
    );
    await screen.findAllByText("Сменить");

    const budget = uxBudgetDelta(document.body, "BillingPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("бюджет не зависит от ЧИСЛА тарифов (BIZ-59)", async () => {
    // Сторож против ловушки, из-за которой экран и попал в долг: кнопка жила
    // внутри повторяющейся карточки, и «главных действий» становилось больше с
    // каждым новым тарифом. На фикстуре из двух это выглядело мелким
    // превышением, на боевых данных превращалось бы в любое число. Проверка
    // мерит тот же экран на впятеро большем списке.
    getBillingPlansMock.mockResolvedValue([
      { code: "basic", name: "Basic", limits: {}, features: {} },
      { code: "pro", name: "Pro", limits: {}, features: {} },
      { code: "team", name: "Team", limits: {}, features: {} },
      { code: "business", name: "Business", limits: {}, features: {} },
      { code: "enterprise", name: "Enterprise", limits: {}, features: {} },
    ]);
    render(
      <MemoryRouter>
        <BillingPage />
      </MemoryRouter>,
    );
    // Четыре «Сменить» и один «Текущий»: у действующего тарифа кнопка занята.
    await waitFor(() => expect(screen.getAllByText("Сменить").length).toBe(4));

    const budget = uxBudgetDelta(document.body, "BillingPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("shows action error and keeps current subscription section visible when mark past due fails", async () => {
    markSubscriptionPastDueMock.mockRejectedValueOnce({
      status: 400,
      message: "mark past due failed",
    });

    render(
      <MemoryRouter>
        <BillingPage />
      </MemoryRouter>,
    );

    await screen.findByText("Тариф и статус");
    fireEvent.click(screen.getByRole("button", { name: "Пометить неоплату" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "mark past due failed",
      );
    });
    expect(screen.getByText(/Статус:/i)).toBeInTheDocument();
    expect(screen.getByText(/План:/i)).toBeInTheDocument();
  });
});
