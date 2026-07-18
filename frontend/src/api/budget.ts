import { apiClient } from "@/api/client";
import type { ApiError } from "@/types/dto/common";
import type { DirectoryItemDto } from "@/types/dto/analytics";
import type {
  BreakdownDimension,
  BudgetArticleCreateInput,
  BudgetArticleDto,
  BudgetArticlePageDto,
  BudgetArticleUpdateInput,
  BudgetBreakdownDto,
  BudgetDomain,
  BudgetExpenseCreateInput,
  BudgetExpenseDto,
  BudgetExpensePageDto,
  BudgetExpenseUpdateInput,
  BudgetOverviewDto,
  BudgetSeedResultDto,
  SafetyBudgetCreateInput,
  SafetyBudgetDetailDto,
  SafetyBudgetDto,
  SafetyBudgetPageDto,
  SafetyBudgetUpdateInput
} from "@/types/dto/budget";

const BASE = "/budget";

export const isFeatureDisabledError = (error: unknown): boolean => {
  const e = error as Partial<ApiError> | null;
  return Boolean(e && e.status === 404 && /feature is not enabled/i.test(e.message ?? ""));
};

export const budgetApi = {
  async getOverview(params: { date_from?: string; date_to?: string } = {}): Promise<BudgetOverviewDto> {
    return (await apiClient.get<BudgetOverviewDto>(`${BASE}/overview`, { params })).data;
  },
  async getBreakdown(params: {
    dimension: BreakdownDimension;
    date_from?: string;
    date_to?: string;
  }): Promise<BudgetBreakdownDto> {
    return (await apiClient.get<BudgetBreakdownDto>(`${BASE}/breakdown`, { params })).data;
  },
  async listBudgets(
    params: { domain?: BudgetDomain; limit?: number; offset?: number } = {}
  ): Promise<SafetyBudgetPageDto> {
    const { data } = await apiClient.get<SafetyBudgetPageDto>(`${BASE}/budgets`, {
      params: { limit: 100, offset: 0, ...params }
    });
    return data;
  },
  async createBudget(payload: SafetyBudgetCreateInput): Promise<SafetyBudgetDto> {
    return (await apiClient.post<SafetyBudgetDto>(`${BASE}/budgets`, payload)).data;
  },
  async getBudget(id: string): Promise<SafetyBudgetDetailDto> {
    return (await apiClient.get<SafetyBudgetDetailDto>(`${BASE}/budgets/${id}`)).data;
  },
  async updateBudget(id: string, payload: SafetyBudgetUpdateInput): Promise<SafetyBudgetDto> {
    return (await apiClient.patch<SafetyBudgetDto>(`${BASE}/budgets/${id}`, payload)).data;
  },
  async deleteBudget(id: string): Promise<void> {
    await apiClient.delete(`${BASE}/budgets/${id}`);
  },
  async listArticles(params: { limit?: number; offset?: number } = {}): Promise<BudgetArticlePageDto> {
    const { data } = await apiClient.get<BudgetArticlePageDto>(`${BASE}/articles`, {
      params: { limit: 200, offset: 0, ...params }
    });
    return data;
  },
  async createArticle(payload: BudgetArticleCreateInput): Promise<BudgetArticleDto> {
    return (await apiClient.post<BudgetArticleDto>(`${BASE}/articles`, payload)).data;
  },
  async updateArticle(id: string, payload: BudgetArticleUpdateInput): Promise<BudgetArticleDto> {
    return (await apiClient.patch<BudgetArticleDto>(`${BASE}/articles/${id}`, payload)).data;
  },
  async deleteArticle(id: string): Promise<void> {
    await apiClient.delete(`${BASE}/articles/${id}`);
  },
  async seedDefaultArticles(): Promise<BudgetSeedResultDto> {
    return (await apiClient.post<BudgetSeedResultDto>(`${BASE}/articles/seed-defaults`)).data;
  },
  async listExpenses(
    params: {
      domain?: BudgetDomain;
      article_id?: string;
      date_from?: string;
      date_to?: string;
      company_id?: string;
      branch_id?: string;
      site_id?: string;
      limit?: number;
      offset?: number;
    } = {}
  ): Promise<BudgetExpensePageDto> {
    const { data } = await apiClient.get<BudgetExpensePageDto>(`${BASE}/expenses`, {
      params: { limit: 100, offset: 0, ...params }
    });
    return data;
  },
  async createExpense(payload: BudgetExpenseCreateInput): Promise<BudgetExpenseDto> {
    return (await apiClient.post<BudgetExpenseDto>(`${BASE}/expenses`, payload)).data;
  },
  async updateExpense(id: string, payload: BudgetExpenseUpdateInput): Promise<BudgetExpenseDto> {
    return (await apiClient.patch<BudgetExpenseDto>(`${BASE}/expenses/${id}`, payload)).data;
  },
  async deleteExpense(id: string): Promise<void> {
    await apiClient.delete(`${BASE}/expenses/${id}`);
  },
  /**
   * Лёгкий справочник филиалов для опционального пикера в ExpenseFormDialog.
   * Компании/объекты уже есть в analyticsApi (getCompanies/getSites — тот же паттерн,
   * что и у ManagementDashboardPage); для филиалов типизированного справочника не было,
   * поэтому добавлен здесь поверх существующего GET /branches (без нового бэкенд-эндпоинта).
   */
  async listBranchesLite(): Promise<{ items?: DirectoryItemDto[] }> {
    const { data } = await apiClient.get<{ items?: DirectoryItemDto[] }>("/branches", {
      params: { limit: 200 }
    });
    return data;
  }
};
