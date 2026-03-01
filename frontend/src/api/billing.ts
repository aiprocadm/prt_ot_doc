import { apiClient } from "@/api/client";

export type BillingSummary = {
  plan: { code: string; name: string };
  subscription: { status: string; period_end?: string | null; grace_until?: string | null; auto_renew: boolean };
  limits: Record<string, number | boolean | null>;
  features: Record<string, boolean>;
  usage: Record<string, number | null>;
  remaining: Record<string, number | null>;
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
  const { data } = await apiClient.get<BillingSummary>("/billing/summary");
  return data;
};

export const getBillingInvoices = async (period?: number) => {
  const { data } = await apiClient.get<BillingInvoice[]>("/billing/invoices", { params: period ? { period } : undefined });
  return data;
};

export const changeBillingPlan = async (planCode: string) => {
  const { data } = await apiClient.post<{ status: string; plan_code: string }>(
    "/billing/change-plan",
    { plan_code: planCode },
    { headers: { "Idempotency-Key": `plan-${planCode}-${Date.now()}` } }
  );
  return data;
};
