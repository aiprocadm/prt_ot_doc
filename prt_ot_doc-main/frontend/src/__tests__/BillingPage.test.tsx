import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BillingPage from "@/pages/admin/BillingPage";

const getBillingSummaryMock = vi.fn();
const getBillingInvoicesMock = vi.fn();
const getBillingPlansMock = vi.fn();
const changeBillingPlanMock = vi.fn();
const markSubscriptionPastDueMock = vi.fn();
const markSubscriptionPaidMock = vi.fn();
const suspendSubscriptionMock = vi.fn();
const activateSubscriptionMock = vi.fn();

vi.mock("@/api/billing", () => ({
  getBillingSummary: (...args: unknown[]) => getBillingSummaryMock(...args),
  getBillingInvoices: (...args: unknown[]) => getBillingInvoicesMock(...args),
  getBillingPlans: (...args: unknown[]) => getBillingPlansMock(...args),
  changeBillingPlan: (...args: unknown[]) => changeBillingPlanMock(...args),
  markSubscriptionPastDue: (...args: unknown[]) => markSubscriptionPastDueMock(...args),
  markSubscriptionPaid: (...args: unknown[]) => markSubscriptionPaidMock(...args),
  suspendSubscription: (...args: unknown[]) => suspendSubscriptionMock(...args),
  activateSubscription: (...args: unknown[]) => activateSubscriptionMock(...args),
}));

describe("BillingPage", () => {
  beforeEach(() => {
    getBillingSummaryMock.mockReset();
    getBillingInvoicesMock.mockReset();
    getBillingPlansMock.mockReset();
    changeBillingPlanMock.mockReset();
    markSubscriptionPastDueMock.mockReset();
    markSubscriptionPaidMock.mockReset();
    suspendSubscriptionMock.mockReset();
    activateSubscriptionMock.mockReset();

    getBillingSummaryMock.mockResolvedValue({
      plan: { code: "basic", name: "Basic" },
      subscription: { status: "active", period_start: "2026-03-01", period_end: "2026-03-31", grace_until: null, auto_renew: true },
      limits: { max_generations_per_month: 100, edo_outgoing_per_month: 50, max_s3_bytes: 1000, max_integrations: 5 },
      features: {},
      usage: { docs_generated: 10, edo_outgoing: 5, s3_bytes_used: 100 },
      remaining: {},
    });
    getBillingInvoicesMock.mockResolvedValue([]);
    getBillingPlansMock.mockResolvedValue([
      { code: "basic", name: "Basic", limits: {}, features: {} },
      { code: "pro", name: "Pro", limits: {}, features: {} },
    ]);
  });

  it("shows action error and keeps plan cards visible when plan change fails", async () => {
    changeBillingPlanMock.mockRejectedValueOnce({ status: 500, message: "plan change failed" });

    render(
      <MemoryRouter>
        <BillingPage />
      </MemoryRouter>
    );

    await screen.findByText("Тариф и статус");
    fireEvent.click(screen.getByRole("button", { name: "Сменить" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("plan change failed");
    });
    expect(screen.getByText("Тарифы")).toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();
  });

  it("shows action error and keeps current subscription section visible when mark past due fails", async () => {
    markSubscriptionPastDueMock.mockRejectedValueOnce({ status: 500, message: "mark past due failed" });

    render(
      <MemoryRouter>
        <BillingPage />
      </MemoryRouter>
    );

    await screen.findByText("Тариф и статус");
    fireEvent.click(screen.getByRole("button", { name: "Пометить неоплату" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("mark past due failed");
    });
    expect(screen.getByText(/Статус:/i)).toBeInTheDocument();
    expect(screen.getByText(/План:/i)).toBeInTheDocument();
  });
});