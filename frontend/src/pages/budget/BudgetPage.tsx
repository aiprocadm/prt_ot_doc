import { useCallback, useState } from "react";

import { budgetApi, isFeatureDisabledError } from "@/api/budget";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BudgetsTab } from "@/features/budget/BudgetsTab";
import { OverviewTab } from "@/features/budget/OverviewTab";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import type {
  BudgetArticlePageDto,
  BudgetExpensePageDto,
  BudgetOverviewDto,
  SafetyBudgetPageDto
} from "@/types/dto/budget";

interface BudgetPageData {
  overview: BudgetOverviewDto;
  budgets: SafetyBudgetPageDto;
  articles: BudgetArticlePageDto;
  expenses: BudgetExpensePageDto;
}

const EMPTY_PAGE = { items: [], total: 0, limit: 0, offset: 0 };

const INITIAL_DATA: BudgetPageData = {
  overview: { generated_at: "", date_from: "", date_to: "", domains: [] },
  budgets: EMPTY_PAGE,
  articles: EMPTY_PAGE,
  expenses: EMPTY_PAGE
};

const BudgetPage = () => {
  // Окно дат живёт на уровне страницы, а не внутри вкладки: иначе любой reload()
  // (создание/правка/удаление бюджета, в дальнейшем — расходы и статьи) молча сбрасывал бы
  // выбранный пользователем период обратно к дефолтному календарному году.
  // Имя не `window` — глобальный window нужен вкладкам (window.confirm) и затенять его опасно.
  const [dateWindow, setDateWindow] = useState<{ date_from: string; date_to: string } | null>(null);

  const loader = useCallback(async (): Promise<BudgetPageData> => {
    const [overview, budgets, articles, expenses] = await Promise.all([
      budgetApi.getOverview(dateWindow ?? undefined),
      budgetApi.listBudgets(),
      budgetApi.listArticles(),
      budgetApi.listExpenses()
    ]);
    return { overview, budgets, articles, expenses };
  }, [dateWindow]);

  const budgetRes = useAsyncResource<BudgetPageData>({
    loader,
    initialData: INITIAL_DATA,
    errorMessage: "Не удалось загрузить данные бюджета безопасности"
  });

  if (budgetRes.error && isFeatureDisabledError(budgetRes.error)) {
    return (
      <EmptyState title="Функция недоступна" description="Бюджет безопасности не включён для этого тенанта." />
    );
  }

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Бюджет безопасности"
        description="Плановые бюджеты, статьи и журнал расходов по доменам обучения, медосмотров и мероприятий."
      />

      <ErrorState error={budgetRes.error ?? undefined} onRetry={() => void budgetRes.reload().catch(() => undefined)} />
      {budgetRes.loading ? <LoadingScreen label="Загрузка бюджета" /> : null}

      {!budgetRes.loading && !budgetRes.error ? (
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Сводка</TabsTrigger>
            <TabsTrigger value="budgets">Бюджеты</TabsTrigger>
            <TabsTrigger value="expenses">Расходы</TabsTrigger>
            <TabsTrigger value="articles">Статьи</TabsTrigger>
          </TabsList>
          <TabsContent value="overview" data-testid="budget-tab-overview">
            <OverviewTab overview={budgetRes.data.overview} onWindowChange={setDateWindow} />
          </TabsContent>
          <TabsContent value="budgets" data-testid="budget-tab-budgets">
            <BudgetsTab
              budgets={budgetRes.data.budgets}
              onChanged={() => void budgetRes.reload().catch(() => undefined)}
            />
          </TabsContent>
          <TabsContent value="expenses">
            <div data-testid="budget-tab-expenses" />
          </TabsContent>
          <TabsContent value="articles">
            <div data-testid="budget-tab-articles" />
          </TabsContent>
        </Tabs>
      ) : null}
    </div>
  );
};

export default BudgetPage;
