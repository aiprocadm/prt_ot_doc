import { useCallback, useEffect, useRef, useState } from "react";

import { budgetApi } from "@/api/budget";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ExpenseFormDialog } from "@/features/budget/ExpenseFormDialog";
import { BUDGET_DOMAIN_LABELS, formatRub } from "@/pages/budget/budgetVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ApiError } from "@/types/dto/common";
import type { BudgetArticlePageDto, BudgetDomain, BudgetExpenseDto, BudgetExpensePageDto } from "@/types/dto/budget";

const EXPENSE_DOMAINS: BudgetDomain[] = ["training", "medical", "events"];

const toApiError = (err: unknown, fallback: string): ApiError =>
  err && typeof err === "object" && "message" in err ? (err as ApiError) : { status: 0, message: fallback };

interface Props {
  expenses: BudgetExpensePageDto;
  articles: BudgetArticlePageDto;
  onChanged: () => void;
}

export const ExpensesTab = ({ expenses, articles, onChanged }: Props) => {
  const [domainFilter, setDomainFilter] = useState<BudgetDomain | "">("");
  const [articleFilter, setArticleFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [items, setItems] = useState<BudgetExpenseDto[]>(expenses.items);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<ApiError | null>(null);
  const requestSeq = useRef(0);

  // Каждый фильтр независим (в отличие от Сводки, где обе границы периода обязаны идти
  // парой) — отправляем только непустые поля, иначе пустая строка ушла бы на бэкенд как
  // валидный (но неверный) фильтр.
  const hasFilter = Boolean(domainFilter || articleFilter || dateFrom || dateTo);

  const fetchList = useCallback(() => {
    if (!hasFilter) {
      // Без фильтра — источник истины это props (страница уже загрузила полный список).
      // Инвалидируем незавершённый отфильтрованный запрос: без bump'а его .then() прошёл бы
      // проверку seq и перезаписал только что выставленный полный список.
      requestSeq.current += 1;
      setItems(expenses.items);
      setListError(null);
      setListLoading(false);
      return;
    }
    const seq = ++requestSeq.current;
    setListLoading(true);
    setListError(null);
    const params: { domain?: BudgetDomain; article_id?: string; date_from?: string; date_to?: string } = {};
    if (domainFilter) params.domain = domainFilter;
    if (articleFilter) params.article_id = articleFilter;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    budgetApi
      .listExpenses(params)
      .then((page) => {
        if (seq === requestSeq.current) setItems(page.items);
      })
      .catch((err) => {
        if (seq === requestSeq.current) setListError(toApiError(err, "Не удалось загрузить расходы"));
      })
      .finally(() => {
        if (seq === requestSeq.current) setListLoading(false);
      });
  }, [hasFilter, domainFilter, articleFilter, dateFrom, dateTo, expenses]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const removeExpense = async (expense: BudgetExpenseDto) => {
    if (!window.confirm(`Удалить расход «${expense.title}»?`)) return;
    try {
      await budgetApi.deleteExpense(expense.id);
      onChanged();
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="expense-domain-filter">Домен</Label>
            <select
              id="expense-domain-filter"
              className="h-9 rounded-md border px-3 text-sm"
              value={domainFilter}
              onChange={(e) => setDomainFilter(e.target.value as BudgetDomain | "")}
            >
              <option value="">Все домены</option>
              {EXPENSE_DOMAINS.map((d) => (
                <option key={d} value={d}>
                  {BUDGET_DOMAIN_LABELS[d]}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="expense-article-filter">Статья</Label>
            <select
              id="expense-article-filter"
              className="h-9 rounded-md border px-3 text-sm"
              value={articleFilter}
              onChange={(e) => setArticleFilter(e.target.value)}
            >
              <option value="">Все статьи</option>
              {articles.items.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="expense-date-from">С</Label>
            <Input
              id="expense-date-from"
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="expense-date-to">По</Label>
            <Input id="expense-date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
        </div>
        <Can permission={PERMISSIONS.BUDGET_MANAGE}>
          <ExpenseFormDialog trigger={<Button>Новый расход</Button>} articles={articles} onSubmitted={onChanged} />
        </Can>
      </div>

      <ErrorState error={listError ?? undefined} onRetry={fetchList} />
      {listLoading ? <LoadingScreen label="Загрузка расходов" /> : null}

      {!listLoading && !listError && items.length === 0 ? (
        <EmptyState title="Расходов нет" description="Добавьте первый расход." />
      ) : null}

      {!listLoading && !listError && items.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-4">Дата</th>
                <th className="py-2 pr-4">Название</th>
                <th className="py-2 pr-4">Домен</th>
                <th className="py-2 pr-4">Статья</th>
                <th className="py-2 pr-4">Сумма</th>
                <th className="py-2">Действия</th>
              </tr>
            </thead>
            <tbody>
              {items.map((expense) => (
                <tr key={expense.id} className="border-b last:border-0">
                  <td className="py-2 pr-4">{expense.occurred_on}</td>
                  <td className="py-2 pr-4">{expense.title}</td>
                  <td className="py-2 pr-4">{BUDGET_DOMAIN_LABELS[expense.domain]}</td>
                  <td className="py-2 pr-4">{expense.article_name ?? "— без статьи"}</td>
                  <td className="py-2 pr-4">{formatRub(expense.amount)}</td>
                  <td className="py-2">
                    <Can permission={PERMISSIONS.BUDGET_MANAGE}>
                      <div className="flex flex-wrap gap-1">
                        <ExpenseFormDialog
                          trigger={
                            <Button size="sm" variant="outline">
                              Изменить
                            </Button>
                          }
                          initialData={expense}
                          articles={articles}
                          onSubmitted={onChanged}
                        />
                        <Button size="sm" variant="destructive" onClick={() => void removeExpense(expense)}>
                          Удалить
                        </Button>
                      </div>
                    </Can>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
};
