import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { budgetApi } from "@/api/budget";
import type {
  BudgetBreakdownDto,
  BudgetOverviewDto,
  SafetyBudgetDetailDto,
  SafetyBudgetPageDto
} from "@/types/dto/budget";

import BudgetPage from "./BudgetPage";

vi.mock("@/api/budget", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/budget")>();
  return {
    ...actual,
    budgetApi: {
      getOverview: vi.fn(),
      getBreakdown: vi.fn(),
      listBudgets: vi.fn(),
      createBudget: vi.fn(),
      getBudget: vi.fn(),
      updateBudget: vi.fn(),
      deleteBudget: vi.fn(),
      listArticles: vi.fn(),
      createArticle: vi.fn(),
      updateArticle: vi.fn(),
      deleteArticle: vi.fn(),
      seedDefaultArticles: vi.fn(),
      listExpenses: vi.fn(),
      createExpense: vi.fn(),
      updateExpense: vi.fn(),
      deleteExpense: vi.fn()
    }
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function" ? (children as (allowed: boolean) => unknown)(true) : children
}));

const EMPTY_PAGE = { items: [], total: 0, limit: 0, offset: 0 };

const OVERVIEW: BudgetOverviewDto = {
  generated_at: "2026-07-18T00:00:00Z",
  date_from: "2026-01-01",
  date_to: "2026-12-31",
  domains: [
    {
      domain: "training",
      read_only: false,
      planned: 100000,
      actual: 40000,
      remaining: 60000,
      budgets: [
        {
          id: "bt1",
          name: "Обучение 2026",
          period_start: "2026-01-01",
          period_end: "2026-12-31",
          planned_amount: 100000,
          actual_own_period: 40000,
          remaining: 60000
        }
      ]
    },
    { domain: "medical", read_only: false, planned: 50000, actual: 60000, remaining: -10000, budgets: [] },
    { domain: "events", read_only: false, planned: 20000, actual: 5000, remaining: 15000, budgets: [] },
    {
      domain: "ppe",
      read_only: true,
      planned: 0,
      actual: 30000,
      remaining: -30000,
      warning_unpriced_receipts: 3,
      budgets: []
    }
  ]
};

const BREAKDOWN_BY_DIMENSION: Record<string, BudgetBreakdownDto> = {
  article: {
    dimension: "article",
    date_from: "2026-01-01",
    date_to: "2026-12-31",
    total: 2,
    items: [
      { id: "art1", name: "Обучение по ОТ", amount: 40000 },
      { id: "", name: "— без статьи", amount: 5000 }
    ]
  },
  domain: {
    dimension: "domain",
    date_from: "2026-01-01",
    date_to: "2026-12-31",
    total: 1,
    items: [{ id: "training", name: "Обучение", amount: 40000 }]
  },
  company: { dimension: "company", date_from: "2026-01-01", date_to: "2026-12-31", total: 0, items: [] },
  branch: { dimension: "branch", date_from: "2026-01-01", date_to: "2026-12-31", total: 0, items: [] },
  site: { dimension: "site", date_from: "2026-01-01", date_to: "2026-12-31", total: 0, items: [] }
};

const BUDGETS_PAGE: SafetyBudgetPageDto = {
  items: [
    {
      id: "bt1",
      name: "Обучение 2026",
      domain: "training",
      period_start: "2026-01-01",
      period_end: "2026-12-31",
      planned_amount: 100000,
      notes: null
    }
  ],
  total: 1,
  limit: 100,
  offset: 0
};

const BUDGET_DETAIL: SafetyBudgetDetailDto = {
  ...BUDGETS_PAGE.items[0],
  actual_total: 40000,
  remaining: 60000,
  expense_count: 3,
  by_article: [{ article_id: "art1", article_name: "Обучение по ОТ", amount: 40000 }]
};

const FEATURE_OFF_ERROR = { status: 404, message: "Budget feature is not enabled for this tenant" };

beforeEach(() => {
  vi.clearAllMocks();
  (budgetApi.getOverview as any).mockResolvedValue(OVERVIEW);
  (budgetApi.getBreakdown as any).mockImplementation(({ dimension }: { dimension: string }) =>
    Promise.resolve(BREAKDOWN_BY_DIMENSION[dimension])
  );
  (budgetApi.listBudgets as any).mockResolvedValue(BUDGETS_PAGE);
  (budgetApi.getBudget as any).mockResolvedValue(BUDGET_DETAIL);
  (budgetApi.listArticles as any).mockResolvedValue(EMPTY_PAGE);
  (budgetApi.listExpenses as any).mockResolvedValue(EMPTY_PAGE);
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <BudgetPage />
    </MemoryRouter>
  );

const openBudgetsTab = async () => {
  const user = userEvent.setup();
  const tab = await screen.findByRole("tab", { name: "Бюджеты" });
  await user.click(tab);
  await screen.findByText("Обучение 2026", { selector: "td" });
};

describe("BudgetPage", () => {
  it("renders overview with 4 domain cards, ppe warehouse badge and unpriced warning", async () => {
    renderPage();

    expect(await screen.findByText("Обучение")).toBeInTheDocument();
    expect(screen.getByText("Медосмотры")).toBeInTheDocument();
    expect(screen.getByText("Мероприятия")).toBeInTheDocument();
    expect(screen.getByText("СИЗ (склад)")).toBeInTheDocument();

    expect(screen.getByText("ведётся на складе")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть склад" })).toHaveAttribute("href", "/warehouse");
    expect(screen.getByText(/Приходов без цены:\s*3/)).toBeInTheDocument();
  });

  it("loads the article breakdown by default and refetches when switching dimension", async () => {
    renderPage();

    expect(await screen.findByText("Обучение по ОТ")).toBeInTheDocument();
    const emptyBucketRow = screen.getByText("— без статьи");
    expect(emptyBucketRow.closest("tr")?.querySelector("a,button")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "По доменам" }));

    await waitFor(() =>
      expect(budgetApi.getBreakdown).toHaveBeenLastCalledWith({
        dimension: "domain",
        date_from: "2026-01-01",
        date_to: "2026-12-31"
      })
    );
  });

  it("renders the budgets list and opens a budget detail panel", async () => {
    renderPage();
    await openBudgetsTab();

    fireEvent.click(screen.getByRole("button", { name: "Открыть" }));

    await waitFor(() => expect(budgetApi.getBudget).toHaveBeenCalledWith("bt1"));
    expect(await screen.findByText("Детали бюджета")).toBeInTheDocument();
    expect(screen.getByTestId("budget-detail-expense-count")).toHaveTextContent("Записей расходов: 3");
    const byArticleRow = screen.getByText("Обучение по ОТ").closest("tr");
    expect(byArticleRow).not.toBeNull();
  });

  it("creates a budget through BudgetFormDialog with the entered payload", async () => {
    (budgetApi.createBudget as any).mockResolvedValue({
      id: "bt2",
      name: "Тестовый бюджет",
      domain: "training",
      period_start: "2026-02-01",
      period_end: "2026-02-28",
      planned_amount: 12345,
      notes: "заметка"
    });
    renderPage();
    await openBudgetsTab();

    fireEvent.click(screen.getByRole("button", { name: "Новый бюджет" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.change(within(dialog).getByLabelText("Название"), { target: { value: "Тестовый бюджет" } });
    fireEvent.change(within(dialog).getByLabelText("Период с"), { target: { value: "2026-02-01" } });
    fireEvent.change(within(dialog).getByLabelText("Период по"), { target: { value: "2026-02-28" } });
    fireEvent.change(within(dialog).getByLabelText("Плановая сумма"), { target: { value: "12345" } });
    fireEvent.change(within(dialog).getByLabelText("Примечания"), { target: { value: "заметка" } });

    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(budgetApi.createBudget).toHaveBeenCalled());
    expect(budgetApi.createBudget).toHaveBeenCalledWith({
      name: "Тестовый бюджет",
      domain: "training",
      period_start: "2026-02-01",
      period_end: "2026-02-28",
      planned_amount: 12345,
      notes: "заметка"
    });
  });

  it("shows the feature-off empty state when the API answers feature-disabled 404", async () => {
    (budgetApi.getOverview as any).mockRejectedValue(FEATURE_OFF_ERROR);
    (budgetApi.listBudgets as any).mockRejectedValue(FEATURE_OFF_ERROR);
    (budgetApi.listArticles as any).mockRejectedValue(FEATURE_OFF_ERROR);
    (budgetApi.listExpenses as any).mockRejectedValue(FEATURE_OFF_ERROR);
    renderPage();

    expect(await screen.findByText("Функция недоступна")).toBeInTheDocument();
  });
});
