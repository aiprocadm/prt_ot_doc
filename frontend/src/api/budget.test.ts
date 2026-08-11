import { describe, it, expect, vi, beforeEach } from "vitest";

import { apiClient } from "@/api/client";
import { budgetApi, isFeatureDisabledError } from "@/api/budget";
import type {
  BudgetArticleCreateInput,
  BudgetArticleUpdateInput,
  BudgetExpenseCreateInput,
  BudgetExpenseUpdateInput,
  BudgetReimbursementCreateInput,
  BudgetReimbursementUpdateInput,
  SafetyBudgetCreateInput,
  SafetyBudgetUpdateInput
} from "@/types/dto/budget";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  }
}));

beforeEach(() => {
  vi.clearAllMocks();
  (apiClient.get as any).mockResolvedValue({ data: { items: [], total: 0, limit: 0, offset: 0 } });
  (apiClient.post as any).mockResolvedValue({ data: { id: "x" } });
  (apiClient.patch as any).mockResolvedValue({ data: { id: "x" } });
  (apiClient.delete as any).mockResolvedValue({ data: null });
});

describe("budgetApi", () => {
  it("gets overview with optional date window", async () => {
    await budgetApi.getOverview({ date_from: "2026-01-01", date_to: "2026-12-31" });
    expect(apiClient.get).toHaveBeenCalledWith("/budget/overview", {
      params: { date_from: "2026-01-01", date_to: "2026-12-31" }
    });
  });

  it("gets overview with no params", async () => {
    await budgetApi.getOverview();
    expect(apiClient.get).toHaveBeenCalledWith("/budget/overview", { params: {} });
  });

  it("gets breakdown by dimension", async () => {
    await budgetApi.getBreakdown({ dimension: "article" });
    expect(apiClient.get).toHaveBeenCalledWith("/budget/breakdown", {
      params: { dimension: "article" }
    });
  });

  it("lists budgets with default paging", async () => {
    await budgetApi.listBudgets();
    expect(apiClient.get).toHaveBeenCalledWith("/budget/budgets", {
      params: { limit: 100, offset: 0 }
    });
  });

  it("merges paging/domain overrides into listBudgets()", async () => {
    await budgetApi.listBudgets({ domain: "training", limit: 20, offset: 40 });
    expect(apiClient.get).toHaveBeenCalledWith("/budget/budgets", {
      params: { domain: "training", limit: 20, offset: 40 }
    });
  });

  it("creates a budget by posting the body to /budget/budgets", async () => {
    const payload: SafetyBudgetCreateInput = {
      name: "Обучение 2026",
      domain: "training",
      period_start: "2026-01-01",
      period_end: "2026-12-31",
      planned_amount: 100000
    };
    (apiClient.post as any).mockResolvedValue({ data: { ...payload, id: "b1", notes: null } });
    const created = await budgetApi.createBudget(payload);
    expect(apiClient.post).toHaveBeenCalledWith("/budget/budgets", payload);
    expect(created.id).toBe("b1");
  });

  it("gets a budget detail by id", async () => {
    await budgetApi.getBudget("b1");
    expect(apiClient.get).toHaveBeenCalledWith("/budget/budgets/b1");
  });

  it("updates a budget via PATCH", async () => {
    const payload: SafetyBudgetUpdateInput = { planned_amount: 150000 };
    await budgetApi.updateBudget("b1", payload);
    expect(apiClient.patch).toHaveBeenCalledWith("/budget/budgets/b1", payload);
  });

  it("deletes a budget", async () => {
    await budgetApi.deleteBudget("b1");
    expect(apiClient.delete).toHaveBeenCalledWith("/budget/budgets/b1");
  });

  it("lists articles with default paging", async () => {
    await budgetApi.listArticles();
    expect(apiClient.get).toHaveBeenCalledWith("/budget/articles", {
      params: { limit: 200, offset: 0 }
    });
  });

  it("creates an article", async () => {
    const payload: BudgetArticleCreateInput = { code: "TRN", name: "Обучение" };
    await budgetApi.createArticle(payload);
    expect(apiClient.post).toHaveBeenCalledWith("/budget/articles", payload);
  });

  it("updates an article via PATCH", async () => {
    const payload: BudgetArticleUpdateInput = { is_active: false };
    await budgetApi.updateArticle("a1", payload);
    expect(apiClient.patch).toHaveBeenCalledWith("/budget/articles/a1", payload);
  });

  it("deletes an article", async () => {
    await budgetApi.deleteArticle("a1");
    expect(apiClient.delete).toHaveBeenCalledWith("/budget/articles/a1");
  });

  it("seeds default articles with no body", async () => {
    await budgetApi.seedDefaultArticles();
    expect(apiClient.post).toHaveBeenCalledWith("/budget/articles/seed-defaults");
  });

  it("lists expenses with default paging and filters", async () => {
    await budgetApi.listExpenses({ domain: "medical", article_id: "a1" });
    expect(apiClient.get).toHaveBeenCalledWith("/budget/expenses", {
      params: { limit: 100, offset: 0, domain: "medical", article_id: "a1" }
    });
  });

  it("creates an expense", async () => {
    const payload: BudgetExpenseCreateInput = {
      domain: "events",
      title: "Тестирование СИЗ",
      occurred_on: "2026-07-01",
      amount: 5000
    };
    await budgetApi.createExpense(payload);
    expect(apiClient.post).toHaveBeenCalledWith("/budget/expenses", payload);
  });

  it("updates an expense via PATCH", async () => {
    const payload: BudgetExpenseUpdateInput = { amount: 6000 };
    await budgetApi.updateExpense("e1", payload);
    expect(apiClient.patch).toHaveBeenCalledWith("/budget/expenses/e1", payload);
  });

  it("deletes an expense", async () => {
    await budgetApi.deleteExpense("e1");
    expect(apiClient.delete).toHaveBeenCalledWith("/budget/expenses/e1");
  });

  it("lists reimbursements with default paging", async () => {
    await budgetApi.listReimbursements();
    expect(apiClient.get).toHaveBeenCalledWith("/budget/reimbursements", {
      params: { limit: 100, offset: 0 }
    });
  });

  it("merges the status filter and paging overrides into listReimbursements()", async () => {
    await budgetApi.listReimbursements({ status: "submitted", limit: 10, offset: 20 });
    expect(apiClient.get).toHaveBeenCalledWith("/budget/reimbursements", {
      params: { status: "submitted", limit: 10, offset: 20 }
    });
  });

  it("gets a reimbursement detail by id", async () => {
    await budgetApi.getReimbursement("r1");
    expect(apiClient.get).toHaveBeenCalledWith("/budget/reimbursements/r1");
  });

  it("creates a reimbursement", async () => {
    const payload: BudgetReimbursementCreateInput = {
      title: "Возмещение за I квартал",
      period_start: "2026-01-01",
      period_end: "2026-03-31",
      requested_amount: 90000
    };
    await budgetApi.createReimbursement(payload);
    expect(apiClient.post).toHaveBeenCalledWith("/budget/reimbursements", payload);
  });

  it("updates a reimbursement via PATCH", async () => {
    const payload: BudgetReimbursementUpdateInput = { requested_amount: 120000 };
    await budgetApi.updateReimbursement("r1", payload);
    expect(apiClient.patch).toHaveBeenCalledWith("/budget/reimbursements/r1", payload);
  });

  it("deletes a reimbursement", async () => {
    await budgetApi.deleteReimbursement("r1");
    expect(apiClient.delete).toHaveBeenCalledWith("/budget/reimbursements/r1");
  });

  it("attaches an expense to a reimbursement", async () => {
    await budgetApi.addReimbursementItem("r1", "e1");
    expect(apiClient.post).toHaveBeenCalledWith("/budget/reimbursements/r1/items", { expense_id: "e1" });
  });

  it("detaches an expense from a reimbursement", async () => {
    await budgetApi.removeReimbursementItem("r1", "e1");
    expect(apiClient.delete).toHaveBeenCalledWith("/budget/reimbursements/r1/items/e1");
  });

  it("posts an FSM action with an empty body by default", async () => {
    await budgetApi.reimbursementAction("r1", "submit");
    expect(apiClient.post).toHaveBeenCalledWith("/budget/reimbursements/r1/submit", {});
  });

  it("posts approved_amount on approve and decision_reason on reject", async () => {
    await budgetApi.reimbursementAction("r1", "approve", { approved_amount: 5000 });
    expect(apiClient.post).toHaveBeenCalledWith("/budget/reimbursements/r1/approve", {
      approved_amount: 5000
    });

    await budgetApi.reimbursementAction("r1", "reject", { decision_reason: "нет подтверждающих" });
    expect(apiClient.post).toHaveBeenCalledWith("/budget/reimbursements/r1/reject", {
      decision_reason: "нет подтверждающих"
    });

    await budgetApi.reimbursementAction("r1", "pay");
    expect(apiClient.post).toHaveBeenCalledWith("/budget/reimbursements/r1/pay", {});
  });

  it("detects the feature-disabled 404", () => {
    expect(
      isFeatureDisabledError({ status: 404, message: "Budget feature is not enabled for this tenant" })
    ).toBe(true);
    expect(isFeatureDisabledError({ status: 404, message: "Not found" })).toBe(false);
    expect(isFeatureDisabledError({ status: 403, message: "feature is not enabled" })).toBe(false);
    expect(isFeatureDisabledError(undefined)).toBe(false);
  });
});
