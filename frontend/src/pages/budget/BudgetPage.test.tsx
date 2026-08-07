import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { budgetApi } from "@/api/budget";
import { formatRub } from "@/pages/budget/budgetVocab";
import type {
  BudgetArticlePageDto,
  BudgetBreakdownDto,
  BudgetExpensePageDto,
  BudgetOverviewDto,
  BudgetReimbursementDetailDto,
  BudgetReimbursementPageDto,
  SafetyBudgetDetailDto,
  SafetyBudgetPageDto,
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
      deleteExpense: vi.fn(),
      listReimbursements: vi.fn(),
      getReimbursement: vi.fn(),
      createReimbursement: vi.fn(),
      updateReimbursement: vi.fn(),
      deleteReimbursement: vi.fn(),
      addReimbursementItem: vi.fn(),
      removeReimbursementItem: vi.fn(),
      reimbursementAction: vi.fn(),
      listBranchesLite: vi.fn(),
    },
  };
});

// ExpenseFormDialog's optional company/site pickers reuse analyticsApi's directory lookups
// (same pattern as ManagementDashboardPage) — mocked here so opening the dialog never hits
// the network in tests.
const analyticsMock = vi.hoisted(() => ({
  getCompanies: vi.fn(),
  getSites: vi.fn(),
  getContractors: vi.fn(),
}));

vi.mock("@/api/analyticsApi", () => ({ analyticsApi: analyticsMock }));

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function"
      ? (children as (allowed: boolean) => unknown)(true)
      : children,
}));

// ReimbursementsTab валидирует решение (сумма/причина) ДО запроса и сообщает об этом тостом —
// без мока проверить «в сеть не ушло, пользователь предупреждён» нечем.
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock("sonner", () => ({ toast: toastMock, Toaster: () => null }));

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
          remaining: 60000,
        },
      ],
    },
    {
      domain: "medical",
      read_only: false,
      planned: 50000,
      actual: 60000,
      remaining: -10000,
      budgets: [],
    },
    {
      domain: "events",
      read_only: false,
      planned: 20000,
      actual: 5000,
      remaining: 15000,
      budgets: [],
    },
    {
      domain: "ppe",
      read_only: true,
      planned: 0,
      actual: 30000,
      remaining: -30000,
      warning_unpriced_receipts: 3,
      budgets: [],
    },
  ],
};

const BREAKDOWN_BY_DIMENSION: Record<string, BudgetBreakdownDto> = {
  article: {
    dimension: "article",
    date_from: "2026-01-01",
    date_to: "2026-12-31",
    total: 2,
    items: [
      { id: "art1", name: "Обучение по ОТ", amount: 40000 },
      { id: "", name: "— без статьи", amount: 5000 },
    ],
  },
  domain: {
    dimension: "domain",
    date_from: "2026-01-01",
    date_to: "2026-12-31",
    total: 1,
    items: [{ id: "training", name: "Обучение", amount: 40000 }],
  },
  company: {
    dimension: "company",
    date_from: "2026-01-01",
    date_to: "2026-12-31",
    total: 0,
    items: [],
  },
  branch: {
    dimension: "branch",
    date_from: "2026-01-01",
    date_to: "2026-12-31",
    total: 0,
    items: [],
  },
  site: {
    dimension: "site",
    date_from: "2026-01-01",
    date_to: "2026-12-31",
    total: 0,
    items: [],
  },
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
      notes: null,
    },
  ],
  total: 1,
  limit: 100,
  offset: 0,
};

const BUDGET_DETAIL: SafetyBudgetDetailDto = {
  ...BUDGETS_PAGE.items[0],
  actual_total: 40000,
  remaining: 60000,
  expense_count: 3,
  by_article: [
    { article_id: "art1", article_name: "Обучение по ОТ", amount: 40000 },
  ],
};

const ARTICLES_PAGE: BudgetArticlePageDto = {
  items: [
    {
      id: "art1",
      code: "TRN-001",
      name: "Обучение по ОТ",
      domain: "training",
      is_active: true,
    },
    {
      id: "art2",
      code: "EVT-001",
      name: "Мероприятия по ОТ",
      domain: "events",
      is_active: true,
    },
    {
      id: "art3",
      code: "UNI-001",
      name: "Универсальная статья",
      domain: null,
      is_active: true,
    },
    {
      id: "art4",
      code: "MED-001",
      name: "Медосмотр (неактивна)",
      domain: "medical",
      is_active: false,
    },
  ],
  total: 4,
  limit: 200,
  offset: 0,
};

const EXPENSES_PAGE: BudgetExpensePageDto = {
  items: [
    {
      id: "exp1",
      domain: "training",
      article_id: "art1",
      article_name: "Обучение по ОТ",
      title: "Курс по ОТ",
      occurred_on: "2026-03-05",
      amount: 15000,
      company_id: null,
      branch_id: null,
      site_id: null,
      entity_type: null,
      entity_id: null,
      notes: null,
    },
    {
      id: "exp2",
      domain: "events",
      article_id: null,
      article_name: null,
      title: "Инструктаж",
      occurred_on: "2026-04-10",
      amount: 3000,
      company_id: null,
      branch_id: null,
      site_id: null,
      entity_type: null,
      entity_id: null,
      notes: null,
    },
  ],
  total: 2,
  limit: 100,
  offset: 0,
};

/** Расход со связанной записью — для проверки снятия связи (оба поля должны уйти в null). */
const LINKED_EXPENSES_PAGE: BudgetExpensePageDto = {
  items: [
    {
      id: "exp9",
      domain: "events",
      article_id: "art2",
      article_name: "Мероприятия по ОТ",
      title: "КМ по предписанию",
      occurred_on: "2026-06-01",
      amount: 7000,
      company_id: null,
      branch_id: null,
      site_id: null,
      entity_type: "corrective_action",
      entity_id: "ca-7",
      notes: null,
    },
  ],
  total: 1,
  limit: 100,
  offset: 0,
};

const REIMBURSEMENT_BASE = {
  reference: null,
  company_id: null,
  decision_reason: null,
  submitted_at: null,
  decided_at: null,
  paid_at: null,
  notes: null,
};

/** Три заявки в разных состояниях FSM — набор действий в строке зависит от статуса. */
const REIMBURSEMENTS_PAGE: BudgetReimbursementPageDto = {
  items: [
    {
      ...REIMBURSEMENT_BASE,
      id: "rb1",
      title: "Возмещение (черновик)",
      status: "draft",
      period_start: "2026-01-01",
      period_end: "2026-06-30",
      requested_amount: 50000,
      approved_amount: null,
      item_count: 1,
      items_amount: 15000,
    },
    {
      ...REIMBURSEMENT_BASE,
      id: "rb2",
      title: "Возмещение (подана)",
      status: "submitted",
      period_start: "2026-01-01",
      period_end: "2026-06-30",
      requested_amount: 90000,
      approved_amount: null,
      submitted_at: "2026-07-01T00:00:00Z",
      item_count: 2,
      items_amount: 90000,
    },
    {
      ...REIMBURSEMENT_BASE,
      id: "rb3",
      title: "Возмещение (одобрена)",
      status: "approved",
      period_start: "2026-01-01",
      period_end: "2026-12-31",
      requested_amount: 202000,
      approved_amount: 180000,
      submitted_at: "2026-06-01T00:00:00Z",
      decided_at: "2026-06-20T00:00:00Z",
      item_count: 2,
      items_amount: 202000,
    },
  ],
  total: 3,
  limit: 100,
  offset: 0,
};

const REIMBURSEMENT_DETAIL: BudgetReimbursementDetailDto = {
  ...REIMBURSEMENTS_PAGE.items[0],
  items: [
    {
      expense_id: "exp1",
      title: "Курс по ОТ",
      domain: "training",
      occurred_on: "2026-03-05",
      amount: 15000,
    },
  ],
};

const FEATURE_OFF_ERROR = {
  status: 404,
  message: "Budget feature is not enabled for this tenant",
};

beforeEach(() => {
  // restoreAllMocks (не clearAllMocks): иначе vi.spyOn(window, "confirm") из delete-тестов
  // остаётся навешанным и протекает в последующие тесты файла.
  vi.restoreAllMocks();
  // toastMock — обычные vi.fn(), restoreAllMocks их не трогает: чистим вызовы вручную.
  toastMock.success.mockClear();
  toastMock.error.mockClear();
  vi.mocked(budgetApi.getOverview).mockResolvedValue(OVERVIEW);
  vi.mocked(budgetApi.getBreakdown).mockImplementation(
    ({ dimension }: { dimension: string }) =>
      Promise.resolve(BREAKDOWN_BY_DIMENSION[dimension]),
  );
  vi.mocked(budgetApi.listBudgets).mockResolvedValue(BUDGETS_PAGE);
  vi.mocked(budgetApi.getBudget).mockResolvedValue(BUDGET_DETAIL);
  vi.mocked(budgetApi.listArticles).mockResolvedValue(EMPTY_PAGE);
  vi.mocked(budgetApi.listExpenses).mockResolvedValue(EMPTY_PAGE);
  vi.mocked(budgetApi.listReimbursements).mockResolvedValue(EMPTY_PAGE);
  vi.mocked(budgetApi.listBranchesLite).mockResolvedValue({ items: [] });
  analyticsMock.getCompanies.mockResolvedValue({ items: [] });
  analyticsMock.getSites.mockResolvedValue({ items: [] });
  analyticsMock.getContractors.mockResolvedValue({ items: [] });
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <BudgetPage />
    </MemoryRouter>,
  );

// getByText's default normalizer collapses whitespace (incl. NBSP) in the DOM text it scans,
// but does NOT run the same normalization over a plain-string matcher — so a matcher built
// from formatRub() (which groups digits with NBSP U+00A0) never equals the collapsed DOM text
// unless we pre-normalize it the same way here.
// Нормализуем ВСЕ пробельные, а не только U+00A0: ICU в CI может отдавать U+202F.
const rub = (value: number) => formatRub(value).replace(/\s/g, " ");

const openBudgetsTab = async () => {
  const user = userEvent.setup();
  const tab = await screen.findByRole("tab", { name: "Бюджеты" });
  await user.click(tab);
  await screen.findByText("Обучение 2026", { selector: "td" });
};

const openExpensesTab = async () => {
  const user = userEvent.setup();
  const tab = await screen.findByRole("tab", { name: "Расходы" });
  await user.click(tab);
};

const openArticlesTab = async () => {
  const user = userEvent.setup();
  const tab = await screen.findByRole("tab", { name: "Статьи" });
  await user.click(tab);
};

const openReimbursementsTab = async () => {
  const user = userEvent.setup();
  const tab = await screen.findByRole("tab", { name: "Возмещения СФР" });
  await user.click(tab);
};

/** Строка заявки в таблице — действия зависят от статуса, поэтому ищем их внутри строки. */
const reimbursementRow = (title: string) =>
  screen.getByText(title).closest("tr") as HTMLElement;

describe("BudgetPage", () => {
  it("renders overview with 4 domain cards, ppe warehouse badge and unpriced warning", async () => {
    renderPage();

    expect(await screen.findByText("Обучение")).toBeInTheDocument();
    expect(screen.getByText("Медосмотры")).toBeInTheDocument();
    expect(screen.getByText("Мероприятия")).toBeInTheDocument();
    expect(screen.getByText("СИЗ (склад)")).toBeInTheDocument();

    expect(screen.getByText("ведётся на складе")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть склад" })).toHaveAttribute(
      "href",
      "/warehouse",
    );
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
        date_to: "2026-12-31",
      }),
    );
  });

  it("keeps the applied period across a reload triggered by a mutation", async () => {
    renderPage();
    await screen.findByText("Обучение");

    fireEvent.change(screen.getByLabelText("С"), {
      target: { value: "2026-03-01" },
    });
    fireEvent.change(screen.getByLabelText("По"), {
      target: { value: "2026-03-31" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));

    const applied = { date_from: "2026-03-01", date_to: "2026-03-31" };
    await waitFor(() =>
      expect(budgetApi.getOverview).toHaveBeenLastCalledWith(applied),
    );

    // Мутация на вкладке «Бюджеты» дёргает reload() всей страницы — окно должно пережить его,
    // а не откатиться к дефолтному календарному году.
    await openBudgetsTab();
    vi.mocked(budgetApi.deleteBudget).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() =>
      expect(budgetApi.deleteBudget).toHaveBeenCalledWith("bt1"),
    );
    await waitFor(() =>
      expect(budgetApi.getOverview).toHaveBeenLastCalledWith(applied),
    );
  });

  it("disables «Применить» while either date bound is empty", async () => {
    renderPage();
    await screen.findByText("Обучение");

    expect(screen.getByRole("button", { name: "Применить" })).toBeEnabled();
    fireEvent.change(screen.getByLabelText("С"), { target: { value: "" } });
    expect(screen.getByRole("button", { name: "Применить" })).toBeDisabled();
  });

  it("renders the budgets list and opens a budget detail panel", async () => {
    renderPage();
    await openBudgetsTab();

    fireEvent.click(screen.getByRole("button", { name: "Открыть" }));

    await waitFor(() =>
      expect(budgetApi.getBudget).toHaveBeenCalledWith("bt1"),
    );
    // «Детали бюджета» появляется сразу по selectedId, ДО ответа getBudget —
    // ждём сам контент деталей, иначе синхронные getBy* давали гонку на CI.
    expect(
      await screen.findByTestId("budget-detail-expense-count"),
    ).toHaveTextContent("Записей расходов: 3");
    expect(screen.getByText("Детали бюджета")).toBeInTheDocument();
    const byArticleRow = screen.getByText("Обучение по ОТ").closest("tr");
    expect(byArticleRow).not.toBeNull();
  });

  it("creates a budget through BudgetFormDialog with the entered payload", async () => {
    vi.mocked(budgetApi.createBudget).mockResolvedValue({
      id: "bt2",
      name: "Тестовый бюджет",
      domain: "training",
      period_start: "2026-02-01",
      period_end: "2026-02-28",
      planned_amount: 12345,
      notes: "заметка",
    });
    renderPage();
    await openBudgetsTab();

    fireEvent.click(screen.getByRole("button", { name: "Новый бюджет" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.change(within(dialog).getByLabelText("Название"), {
      target: { value: "Тестовый бюджет" },
    });
    fireEvent.change(within(dialog).getByLabelText("Период с"), {
      target: { value: "2026-02-01" },
    });
    fireEvent.change(within(dialog).getByLabelText("Период по"), {
      target: { value: "2026-02-28" },
    });
    fireEvent.change(within(dialog).getByLabelText("Плановая сумма"), {
      target: { value: "12345" },
    });
    fireEvent.change(within(dialog).getByLabelText("Примечания"), {
      target: { value: "заметка" },
    });

    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(budgetApi.createBudget).toHaveBeenCalled());
    expect(budgetApi.createBudget).toHaveBeenCalledWith({
      name: "Тестовый бюджет",
      domain: "training",
      period_start: "2026-02-01",
      period_end: "2026-02-28",
      planned_amount: 12345,
      notes: "заметка",
    });
    // Дожидаемся, пока onSubmitted -> reload() досчитается: иначе состояние допишется уже
    // после конца теста и полный прогон (Task 11) засыпет консоль act()-варнингами.
    await waitFor(() => expect(budgetApi.getOverview).toHaveBeenCalledTimes(2));
  });

  it("sends only the changed fields when editing a budget", async () => {
    vi.mocked(budgetApi.updateBudget).mockResolvedValue({
      ...BUDGETS_PAGE.items[0],
      planned_amount: 999,
    });
    renderPage();
    await openBudgetsTab();

    fireEvent.click(screen.getByRole("button", { name: "Изменить" }));
    const dialog = await screen.findByRole("dialog");

    // Домен иммутабелен на бэкенде — селект должен быть заблокирован в режиме правки.
    expect(within(dialog).getByLabelText("Домен")).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText("Плановая сумма"), {
      target: { value: "999" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(budgetApi.updateBudget).toHaveBeenCalled());
    expect(budgetApi.updateBudget).toHaveBeenCalledWith("bt1", {
      planned_amount: 999,
    });
    await waitFor(() => expect(budgetApi.getOverview).toHaveBeenCalledTimes(2));
  });

  it("shows the feature-off empty state when the API answers feature-disabled 404", async () => {
    vi.mocked(budgetApi.getOverview).mockRejectedValue(FEATURE_OFF_ERROR);
    vi.mocked(budgetApi.listBudgets).mockRejectedValue(FEATURE_OFF_ERROR);
    vi.mocked(budgetApi.listArticles).mockRejectedValue(FEATURE_OFF_ERROR);
    vi.mocked(budgetApi.listExpenses).mockRejectedValue(FEATURE_OFF_ERROR);
    vi.mocked(budgetApi.listReimbursements).mockRejectedValue(
      FEATURE_OFF_ERROR,
    );
    renderPage();

    expect(await screen.findByText("Функция недоступна")).toBeInTheDocument();
  });

  it("renders the expenses list; the domain filter refetches without empty date bounds", async () => {
    vi.mocked(budgetApi.listArticles).mockResolvedValue(ARTICLES_PAGE);
    vi.mocked(budgetApi.listExpenses).mockResolvedValue(EXPENSES_PAGE);
    renderPage();
    await openExpensesTab();

    expect(await screen.findByText("Курс по ОТ")).toBeInTheDocument();
    expect(screen.getByText(rub(15000))).toBeInTheDocument();
    expect(screen.getByText("Инструктаж")).toBeInTheDocument();
    expect(screen.getByText("— без статьи")).toBeInTheDocument();

    vi.mocked(budgetApi.listExpenses).mockClear();
    vi.mocked(budgetApi.listExpenses).mockResolvedValue(EXPENSES_PAGE);

    fireEvent.change(screen.getByLabelText("Домен"), {
      target: { value: "training" },
    });

    await waitFor(() => expect(budgetApi.listExpenses).toHaveBeenCalled());
    const params = vi.mocked(budgetApi.listExpenses).mock.calls.at(-1)?.[0];
    expect(params).toEqual({ domain: "training" });
  });

  it("creates an expense with domain-filtered article options and no entity link when unchecked", async () => {
    vi.mocked(budgetApi.listArticles).mockResolvedValue(ARTICLES_PAGE);
    vi.mocked(budgetApi.listExpenses).mockResolvedValue(EXPENSES_PAGE);
    vi.mocked(budgetApi.createExpense).mockResolvedValue({
      ...EXPENSES_PAGE.items[0],
      id: "exp3",
    });
    renderPage();
    await openExpensesTab();
    await screen.findByText("Курс по ОТ");

    fireEvent.click(screen.getByRole("button", { name: "Новый расход" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.change(within(dialog).getByLabelText("Домен"), {
      target: { value: "events" },
    });

    // Домен events -> статья либо events, либо универсальная; training/неактивная medical скрыты.
    expect(within(dialog).getByText("Мероприятия по ОТ")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Универсальная статья"),
    ).toBeInTheDocument();
    expect(
      within(dialog).queryByText("Обучение по ОТ"),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).queryByText("Медосмотр (неактивна)"),
    ).not.toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText("Название"), {
      target: { value: "Инструктаж по электробезопасности" },
    });
    fireEvent.change(within(dialog).getByLabelText("Дата"), {
      target: { value: "2026-05-01" },
    });
    fireEvent.change(within(dialog).getByLabelText("Сумма"), {
      target: { value: "2500" },
    });

    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(budgetApi.createExpense).toHaveBeenCalled());
    expect(budgetApi.createExpense).toHaveBeenCalledWith({
      domain: "events",
      title: "Инструктаж по электробезопасности",
      occurred_on: "2026-05-01",
      amount: 2500,
      article_id: null,
      company_id: null,
      branch_id: null,
      site_id: null,
      notes: null,
    });
    await waitFor(() => expect(budgetApi.getOverview).toHaveBeenCalledTimes(2));
  });

  it("sends entity_type derived from the domain when the entity link checkbox is checked", async () => {
    vi.mocked(budgetApi.listArticles).mockResolvedValue(ARTICLES_PAGE);
    vi.mocked(budgetApi.listExpenses).mockResolvedValue(EXPENSES_PAGE);
    vi.mocked(budgetApi.createExpense).mockResolvedValue({
      ...EXPENSES_PAGE.items[0],
      id: "exp4",
    });
    renderPage();
    await openExpensesTab();
    await screen.findByText("Курс по ОТ");

    fireEvent.click(screen.getByRole("button", { name: "Новый расход" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.change(within(dialog).getByLabelText("Домен"), {
      target: { value: "events" },
    });
    fireEvent.change(within(dialog).getByLabelText("Название"), {
      target: { value: "КП по итогам проверки" },
    });
    fireEvent.change(within(dialog).getByLabelText("Дата"), {
      target: { value: "2026-05-02" },
    });
    fireEvent.change(within(dialog).getByLabelText("Сумма"), {
      target: { value: "1000" },
    });

    fireEvent.click(within(dialog).getByLabelText("Связать с записью"));
    // entity_type read-only и выводится из выбранного домена (events -> corrective_action).
    expect(within(dialog).getByLabelText("Тип записи")).toHaveValue(
      "corrective_action",
    );
    fireEvent.change(within(dialog).getByLabelText("ID записи"), {
      target: { value: "ca-42" },
    });

    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(budgetApi.createExpense).toHaveBeenCalled());
    expect(budgetApi.createExpense).toHaveBeenCalledWith({
      domain: "events",
      title: "КП по итогам проверки",
      occurred_on: "2026-05-02",
      amount: 1000,
      article_id: null,
      company_id: null,
      branch_id: null,
      site_id: null,
      notes: null,
      entity_type: "corrective_action",
      entity_id: "ca-42",
    });
  });

  it("deletes an expense after confirm and reloads", async () => {
    vi.mocked(budgetApi.listArticles).mockResolvedValue(ARTICLES_PAGE);
    vi.mocked(budgetApi.listExpenses).mockResolvedValue(EXPENSES_PAGE);
    vi.mocked(budgetApi.deleteExpense).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    await openExpensesTab();
    await screen.findByText("Курс по ОТ");

    const row = screen.getByText("Курс по ОТ").closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(
      within(row as HTMLElement).getByRole("button", { name: "Удалить" }),
    );

    await waitFor(() =>
      expect(budgetApi.deleteExpense).toHaveBeenCalledWith("exp1"),
    );
    await waitFor(() => expect(budgetApi.getOverview).toHaveBeenCalledTimes(2));
  });

  it("renders the articles list and seeds default articles then reloads", async () => {
    vi.mocked(budgetApi.listArticles).mockResolvedValue(ARTICLES_PAGE);
    vi.mocked(budgetApi.seedDefaultArticles).mockResolvedValue({
      created: 5,
      skipped: 2,
    });
    renderPage();
    await openArticlesTab();

    expect(await screen.findByText("Универсальная статья")).toBeInTheDocument();
    expect(screen.getByText("Универсальная")).toBeInTheDocument();
    expect(screen.getByText("Отключена")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Заполнить стандартными" }),
    );

    await waitFor(() =>
      expect(budgetApi.seedDefaultArticles).toHaveBeenCalled(),
    );
    await waitFor(() => expect(budgetApi.getOverview).toHaveBeenCalledTimes(2));
  });

  it("stays on the active tab and keeps filters across a mutation-triggered reload", async () => {
    vi.mocked(budgetApi.listArticles).mockResolvedValue(ARTICLES_PAGE);
    vi.mocked(budgetApi.listExpenses).mockResolvedValue(EXPENSES_PAGE);
    vi.mocked(budgetApi.deleteExpense).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    await openExpensesTab();
    await screen.findByText("Курс по ОТ");

    fireEvent.change(screen.getByLabelText("Домен"), {
      target: { value: "training" },
    });
    await waitFor(() =>
      expect(budgetApi.listExpenses).toHaveBeenCalledWith({
        domain: "training",
      }),
    );

    const row = screen.getByText("Курс по ОТ").closest("tr");
    fireEvent.click(
      within(row as HTMLElement).getByRole("button", { name: "Удалить" }),
    );
    await waitFor(() => expect(budgetApi.getOverview).toHaveBeenCalledTimes(2));

    // Раньше reload() ставил loading=true и всё поддерево <Tabs> размонтировалось:
    // активная вкладка отваливалась на «Сводку», а фильтры расходов сбрасывались.
    expect(screen.getByRole("tab", { name: "Расходы" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Домен")).toHaveValue("training"),
    );
  });

  it("clears BOTH entity fields when unchecking the link on an already-linked expense", async () => {
    vi.mocked(budgetApi.listArticles).mockResolvedValue(ARTICLES_PAGE);
    vi.mocked(budgetApi.listExpenses).mockResolvedValue(LINKED_EXPENSES_PAGE);
    vi.mocked(budgetApi.updateExpense).mockResolvedValue(
      LINKED_EXPENSES_PAGE.items[0],
    );
    renderPage();
    await openExpensesTab();
    await screen.findByText("КМ по предписанию");

    const row = screen.getByText("КМ по предписанию").closest("tr");
    fireEvent.click(
      within(row as HTMLElement).getByRole("button", { name: "Изменить" }),
    );
    const dialog = await screen.findByRole("dialog");

    // Диалог открылся с уже проставленной связью.
    const linkCheckbox = within(dialog).getByLabelText("Связать с записью");
    expect(linkCheckbox).toBeChecked();
    expect(within(dialog).getByLabelText("ID записи")).toHaveValue("ca-7");

    fireEvent.click(linkCheckbox);
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(budgetApi.updateExpense).toHaveBeenCalled());
    // Бэкенд проверяет пару целиком: снять связь можно только обнулив ОБА поля.
    expect(budgetApi.updateExpense).toHaveBeenCalledWith("exp9", {
      entity_type: null,
      entity_id: null,
    });
  });

  it("resets the picked article when the domain changes on create", async () => {
    vi.mocked(budgetApi.listArticles).mockResolvedValue(ARTICLES_PAGE);
    vi.mocked(budgetApi.listExpenses).mockResolvedValue(EXPENSES_PAGE);
    vi.mocked(budgetApi.createExpense).mockResolvedValue({
      ...EXPENSES_PAGE.items[0],
      id: "exp5",
    });
    renderPage();
    await openExpensesTab();
    await screen.findByText("Курс по ОТ");

    fireEvent.click(screen.getByRole("button", { name: "Новый расход" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.change(within(dialog).getByLabelText("Домен"), {
      target: { value: "events" },
    });
    const articleSelect = within(dialog).getByLabelText("Статья");
    fireEvent.change(articleSelect, { target: { value: "art2" } });
    expect(articleSelect).toHaveValue("art2");

    // Смена домена делает выбранную статью невалидной -> выбор должен сброситься в state,
    // а не просто исчезнуть из списка опций (иначе ушёл бы 422 article_domain_mismatch).
    fireEvent.change(within(dialog).getByLabelText("Домен"), {
      target: { value: "training" },
    });
    expect(articleSelect).toHaveValue("");

    fireEvent.change(within(dialog).getByLabelText("Название"), {
      target: { value: "Курс" },
    });
    fireEvent.change(within(dialog).getByLabelText("Дата"), {
      target: { value: "2026-05-03" },
    });
    fireEvent.change(within(dialog).getByLabelText("Сумма"), {
      target: { value: "500" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(budgetApi.createExpense).toHaveBeenCalled());
    expect(
      vi.mocked(budgetApi.createExpense).mock.calls.at(-1)?.[0],
    ).toMatchObject({
      domain: "training",
      article_id: null,
    });
  });

  it("renders reimbursements with status-dependent actions", async () => {
    vi.mocked(budgetApi.listReimbursements).mockResolvedValue(
      REIMBURSEMENTS_PAGE,
    );
    renderPage();
    await openReimbursementsTab();

    expect(
      await screen.findByText("Возмещение (черновик)"),
    ).toBeInTheDocument();
    expect(screen.getByText(rub(180000))).toBeInTheDocument();

    // draft: правка/удаление/подача разрешены.
    const draft = within(reimbursementRow("Возмещение (черновик)"));
    expect(draft.getByRole("button", { name: "Подать" })).toBeInTheDocument();
    expect(draft.getByRole("button", { name: "Изменить" })).toBeInTheDocument();
    expect(draft.getByRole("button", { name: "Удалить" })).toBeInTheDocument();
    expect(draft.getByText("—")).toBeInTheDocument(); // одобренной суммы ещё нет

    // submitted: бэкенд отдаст 409 на правку — кнопок правки/удаления быть не должно.
    const submitted = within(reimbursementRow("Возмещение (подана)"));
    expect(
      submitted.getByRole("button", { name: "Одобрить" }),
    ).toBeInTheDocument();
    expect(
      submitted.getByRole("button", { name: "Отклонить" }),
    ).toBeInTheDocument();
    expect(
      submitted.queryByRole("button", { name: "Изменить" }),
    ).not.toBeInTheDocument();
    expect(
      submitted.queryByRole("button", { name: "Удалить" }),
    ).not.toBeInTheDocument();

    const approved = within(reimbursementRow("Возмещение (одобрена)"));
    expect(
      approved.getByRole("button", { name: "Выплатить" }),
    ).toBeInTheDocument();
    expect(
      approved.queryByRole("button", { name: "Одобрить" }),
    ).not.toBeInTheDocument();
  });

  it("filters reimbursements by status through a dedicated request", async () => {
    vi.mocked(budgetApi.listReimbursements).mockResolvedValue(
      REIMBURSEMENTS_PAGE,
    );
    renderPage();
    await openReimbursementsTab();
    await screen.findByText("Возмещение (черновик)");

    vi.mocked(budgetApi.listReimbursements).mockResolvedValue({
      ...EMPTY_PAGE,
      limit: 100,
    });
    fireEvent.change(screen.getByLabelText("Статус"), {
      target: { value: "paid" },
    });

    await waitFor(() =>
      expect(budgetApi.listReimbursements).toHaveBeenLastCalledWith({
        status: "paid",
      }),
    );
    // Пустой результат ПОД фильтром — отдельная подсказка, а не «заявок нет вообще».
    expect(
      await screen.findByText("Ничего не найдено по фильтру"),
    ).toBeInTheDocument();
  });

  it("runs a no-input FSM action directly and reloads", async () => {
    vi.mocked(budgetApi.listReimbursements).mockResolvedValue(
      REIMBURSEMENTS_PAGE,
    );
    vi.mocked(budgetApi.reimbursementAction).mockResolvedValue(
      REIMBURSEMENTS_PAGE.items[1],
    );
    renderPage();
    await openReimbursementsTab();
    await screen.findByText("Возмещение (черновик)");

    fireEvent.click(
      within(reimbursementRow("Возмещение (черновик)")).getByRole("button", {
        name: "Подать",
      }),
    );

    await waitFor(() =>
      expect(budgetApi.reimbursementAction).toHaveBeenCalledWith(
        "rb1",
        "submit",
      ),
    );
    await waitFor(() => expect(budgetApi.getOverview).toHaveBeenCalledTimes(2));
  });

  it("prefills the approve dialog and refuses an amount above the requested one", async () => {
    vi.mocked(budgetApi.listReimbursements).mockResolvedValue(
      REIMBURSEMENTS_PAGE,
    );
    vi.mocked(budgetApi.reimbursementAction).mockResolvedValue(
      REIMBURSEMENTS_PAGE.items[2],
    );
    renderPage();
    await openReimbursementsTab();
    await screen.findByText("Возмещение (подана)");

    fireEvent.click(
      within(reimbursementRow("Возмещение (подана)")).getByRole("button", {
        name: "Одобрить",
      }),
    );
    const dialog = await screen.findByRole("dialog");
    const amount = within(dialog).getByLabelText("Одобренная сумма");
    expect(amount).toHaveValue(90000); // по умолчанию — запрошенная сумма

    fireEvent.change(amount, { target: { value: "999999" } });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Подтвердить" }),
    );

    // Бэкенд ответил бы 422 approved_amount_invalid — форма не должна доводить до запроса.
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled());
    expect(budgetApi.reimbursementAction).not.toHaveBeenCalled();

    fireEvent.change(amount, { target: { value: "70000" } });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Подтвердить" }),
    );

    await waitFor(() =>
      expect(budgetApi.reimbursementAction).toHaveBeenCalledWith(
        "rb2",
        "approve",
        { approved_amount: 70000 },
      ),
    );
  });

  it("requires a reason before rejecting", async () => {
    vi.mocked(budgetApi.listReimbursements).mockResolvedValue(
      REIMBURSEMENTS_PAGE,
    );
    vi.mocked(budgetApi.reimbursementAction).mockResolvedValue({
      ...REIMBURSEMENTS_PAGE.items[1],
      status: "rejected",
    });
    renderPage();
    await openReimbursementsTab();
    await screen.findByText("Возмещение (подана)");

    fireEvent.click(
      within(reimbursementRow("Возмещение (подана)")).getByRole("button", {
        name: "Отклонить",
      }),
    );
    const dialog = await screen.findByRole("dialog");

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Подтвердить" }),
    );
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled());
    expect(budgetApi.reimbursementAction).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText("Причина отклонения"), {
      target: { value: "  Нет документов  " },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Подтвердить" }),
    );

    await waitFor(() =>
      expect(budgetApi.reimbursementAction).toHaveBeenCalledWith(
        "rb2",
        "reject",
        {
          decision_reason: "Нет документов",
        },
      ),
    );
  });

  it("opens a claim, attaches an expense and hides already-linked ones from the picker", async () => {
    vi.mocked(budgetApi.listReimbursements).mockResolvedValue(
      REIMBURSEMENTS_PAGE,
    );
    vi.mocked(budgetApi.listExpenses).mockResolvedValue(EXPENSES_PAGE);
    vi.mocked(budgetApi.getReimbursement).mockResolvedValue(
      REIMBURSEMENT_DETAIL,
    );
    // Ручка возвращает Promise<void> — резолвим undefined, а не «созданный» item.
    vi.mocked(budgetApi.addReimbursementItem).mockResolvedValue(undefined);
    renderPage();
    await openReimbursementsTab();
    await screen.findByText("Возмещение (черновик)");

    fireEvent.click(
      within(reimbursementRow("Возмещение (черновик)")).getByRole("button", {
        name: "Открыть",
      }),
    );

    await waitFor(() =>
      expect(budgetApi.getReimbursement).toHaveBeenCalledWith("rb1"),
    );
    // «Детали заявки» появляется сразу по selectedId, ДО ответа getReimbursement —
    // ждём сам контент деталей, иначе синхронные getBy* давали гонку на CI.
    expect(
      await screen.findByTestId("reimbursement-detail-item-count"),
    ).toHaveTextContent("Записей расходов: 1");
    expect(screen.getByText("Детали заявки")).toBeInTheDocument();

    // exp1 уже в заявке — в пикере остаётся только exp2.
    const picker = screen.getByLabelText("Добавить расход");
    expect(within(picker).queryByText(/Курс по ОТ/)).not.toBeInTheDocument();
    expect(within(picker).getByText(/Инструктаж/)).toBeInTheDocument();

    fireEvent.change(picker, { target: { value: "exp2" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить" }));

    await waitFor(() =>
      expect(budgetApi.addReimbursementItem).toHaveBeenCalledWith(
        "rb1",
        "exp2",
      ),
    );
    await waitFor(() => expect(budgetApi.getOverview).toHaveBeenCalledTimes(2));
  });

  it("detaches an expense from an open draft claim", async () => {
    vi.mocked(budgetApi.listReimbursements).mockResolvedValue(
      REIMBURSEMENTS_PAGE,
    );
    vi.mocked(budgetApi.listExpenses).mockResolvedValue(EXPENSES_PAGE);
    vi.mocked(budgetApi.getReimbursement).mockResolvedValue(
      REIMBURSEMENT_DETAIL,
    );
    vi.mocked(budgetApi.removeReimbursementItem).mockResolvedValue(undefined);
    renderPage();
    await openReimbursementsTab();
    await screen.findByText("Возмещение (черновик)");

    fireEvent.click(
      within(reimbursementRow("Возмещение (черновик)")).getByRole("button", {
        name: "Открыть",
      }),
    );
    // «Детали заявки» появляется сразу по selectedId, ДО ответа getReimbursement —
    // кнопка «Убрать» живёт в списке позиций под гейтом загрузки, ждём её саму.
    fireEvent.click(await screen.findByRole("button", { name: "Убрать" }));

    await waitFor(() =>
      expect(budgetApi.removeReimbursementItem).toHaveBeenCalledWith(
        "rb1",
        "exp1",
      ),
    );
  });

  it("deletes a draft claim after confirm", async () => {
    vi.mocked(budgetApi.listReimbursements).mockResolvedValue(
      REIMBURSEMENTS_PAGE,
    );
    vi.mocked(budgetApi.deleteReimbursement).mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    await openReimbursementsTab();
    await screen.findByText("Возмещение (черновик)");

    fireEvent.click(
      within(reimbursementRow("Возмещение (черновик)")).getByRole("button", {
        name: "Удалить",
      }),
    );

    await waitFor(() =>
      expect(budgetApi.deleteReimbursement).toHaveBeenCalledWith("rb1"),
    );
    await waitFor(() => expect(budgetApi.getOverview).toHaveBeenCalledTimes(2));
  });

  it("disables the code field when editing an article", async () => {
    vi.mocked(budgetApi.listArticles).mockResolvedValue(ARTICLES_PAGE);
    renderPage();
    await openArticlesTab();
    await screen.findByText("Универсальная статья");

    const row = screen.getByText("Универсальная статья").closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(
      within(row as HTMLElement).getByRole("button", { name: "Изменить" }),
    );

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Код")).toBeDisabled();
  });
});
