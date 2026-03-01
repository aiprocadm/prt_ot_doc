import { apiClient } from "@/api/client";

export type BillingSummary = {
  plan: { code: string; name: string };
  subscription: { status: string; period_end?: string | null; grace_until?: string | null; auto_renew: boolean };
  limits: Record<string, number | boolean | null>;
  features: Record<string, boolean>;
  usage: Record<string, number | null>;
  remaining: Record<string, number | null>;
};

export const getBillingSummary = async () => {
  const { data } = await apiClient.get<BillingSummary>("/billing/summary");
  return data;
};
