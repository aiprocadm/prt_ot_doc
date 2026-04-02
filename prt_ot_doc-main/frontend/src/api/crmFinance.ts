import { apiClient } from "@/api/client";

export type CrmFinanceContract = {
  id: string;
  company_id: string;
  title: string;
  counterparty_name: string;
  contract_number: string | null;
  status: string;
  total_amount: number | null;
  currency: string;
  valid_until: string | null;
};

export type CrmFinanceOrder = {
  id: string;
  contract_id: string;
  order_number: string;
  status: string;
  total_amount: number | null;
  currency: string;
};

export type CrmFinanceInvoice = {
  id: string;
  contract_id: string;
  order_id: string | null;
  invoice_number: string;
  status: string;
  total_amount: number | null;
  currency: string;
  due_at: string | null;
  paid_at: string | null;
};

export type BillingPlan = {
  code: string;
  name: string;
};

export type BillingSummary = {
  subscription_status?: string | null;
  plan?: BillingPlan | null;
  current_period?: number | null;
  usage?: Record<string, number | null> | null;
  limits?: Record<string, number | null> | null;
};

export type CrmFinanceSnapshot = {
  contracts: CrmFinanceContract[];
  orders: CrmFinanceOrder[];
  invoices: CrmFinanceInvoice[];
  billing: BillingSummary | null;
};

export const crmFinanceApi = {
  async getSnapshot(): Promise<CrmFinanceSnapshot> {
    const [contractsResponse, ordersResponse, invoicesResponse, billingResponse] = await Promise.all([
      apiClient.get<{ items: CrmFinanceContract[] }>("/contracts", { params: { limit: 100, offset: 0 } }),
      apiClient.get<{ items: CrmFinanceOrder[] }>("/orders", { params: { limit: 100, offset: 0 } }),
      apiClient.get<{ items: CrmFinanceInvoice[] }>("/invoices", { params: { limit: 100, offset: 0 } }),
      apiClient.get<BillingSummary>("/billing/plan").catch(() => ({ data: null }))
    ]);

    return {
      contracts: contractsResponse.data.items ?? [],
      orders: ordersResponse.data.items ?? [],
      invoices: invoicesResponse.data.items ?? [],
      billing: billingResponse.data
    };
  }
};
