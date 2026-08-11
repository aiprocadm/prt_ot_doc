import { apiClient } from "@/api/client";

export type BillingSummary = {
  plan: { code: string; name: string };
  subscription: { status: string; period_start?: string | null; period_end?: string | null; grace_until?: string | null; auto_renew: boolean };
  limits: Record<string, number | boolean | null>;
  features: Record<string, boolean>;
  usage: Record<string, number | null>;
  remaining: Record<string, number | null>;
};

export type BillingPlan = {
  code: string;
  name: string;
  limits: Record<string, number | boolean | null>;
  features: Record<string, boolean>;
};

export type BillingInvoice = {
  id: string;
  period_yyyymm: number;
  amount: number;
  status: string;
  due_date: string | null;
  payload: Record<string, unknown>;
};

export const getBillingSummary = async () => {
  const { data } = await apiClient.get<BillingSummary>("/billing/plan");
  return data;
};

export const getBillingInvoices = async (period?: number) => {
  const { data } = await apiClient.get<BillingInvoice[]>("/billing/invoices", { params: period ? { period } : undefined });
  return data;
};

export const getBillingPlans = async () => {
  const { data } = await apiClient.get<BillingPlan[]>("/billing/plans");
  return data;
};

export const changeBillingPlan = async (planCode: string) => {
  const { data } = await apiClient.post<{ status: string; plan_code: string }>(
    "/billing/plan/change",
    { plan_code: planCode },
    { headers: { "Idempotency-Key": `plan-${planCode}-${Date.now()}` } }
  );
  return data;
};

export const markSubscriptionPastDue = async (graceDays = 7) => apiClient.post("/billing/subscription/mark_past_due", { grace_days: graceDays });
export const markSubscriptionPaid = async () => apiClient.post("/billing/subscription/mark_paid");
export const suspendSubscription = async () => apiClient.post("/billing/subscription/suspend");
export const activateSubscription = async () => apiClient.post("/billing/subscription/activate");
