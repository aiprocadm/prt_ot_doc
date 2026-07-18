import { useCallback, useEffect, useRef, useState } from "react";

import { budgetApi } from "@/api/budget";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { BudgetFormDialog } from "@/features/budget/BudgetFormDialog";
import { BUDGET_DOMAIN_LABELS, BUDGET_DOMAINS, formatRub, toApiError } from "@/pages/budget/budgetVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ApiError } from "@/types/dto/common";
import type {
  BudgetDomain,
  SafetyBudgetDetailDto,
  SafetyBudgetDto,
  SafetyBudgetPageDto
} from "@/types/dto/budget";

interface Props {
  budgets: SafetyBudgetPageDto;
  onChanged: () => void;
}

export const BudgetsTab = ({ budgets, onChanged }: Props) => {
  const [domainFilter, setDomainFilter] = useState<BudgetDomain | "">("");
  const [items, setItems] = useState<SafetyBudgetDto[]>(budgets.items);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<ApiError | null>(null);
  const requestSeq = useRef(0);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SafetyBudgetDetailDto | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<ApiError | null>(null);

  // Без фильтра — источник истины это props (страница уже загрузила полный список).
  // С фильтром — свой запрос budgetApi.listBudgets({domain}); перезапускается и при
  // смене фильтра, и при обновлении budgets сверху (после onChanged), чтобы фильтр
  // не «слетал» после создания/изменения/удаления бюджета.
  const fetchList = useCallback(() => {
    if (!domainFilter) {
      // Инвалидируем незавершённый отфильтрованный запрос: без bump'а его .then() прошёл бы
      // проверку seq и перезаписал только что выставленный полный список.
      requestSeq.current += 1;
      setItems(budgets.items);
      setListError(null);
      setListLoading(false);
      return;
    }
    const seq = ++requestSeq.current;
    setListLoading(true);
    setListError(null);
    budgetApi
      .listBudgets({ domain: domainFilter })
      .then((page) => {
        if (seq === requestSeq.current) setItems(page.items);
      })
      .catch((err) => {
        if (seq === requestSeq.current) setListError(toApiError(err, "Не удалось загрузить бюджеты"));
      })
      .finally(() => {
        if (seq === requestSeq.current) setListLoading(false);
      });
  }, [domainFilter, budgets]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const openBudget = useCallback((id: string) => {
    setSelectedId(id);
    setDetail(null);
    setDetailLoading(true);
    setDetailError(null);
    budgetApi
      .getBudget(id)
      .then(setDetail)
      .catch((err) => setDetailError(toApiError(err, "Не удалось загрузить бюджет")))
      .finally(() => setDetailLoading(false));
  }, []);

  const afterMutation = () => {
    onChanged();
    if (selectedId) openBudget(selectedId);
  };

  const removeBudget = async (budget: SafetyBudgetDto) => {
    if (!window.confirm(`Удалить бюджет «${budget.name}»?`)) return;
    try {
      await budgetApi.deleteBudget(budget.id);
      if (selectedId === budget.id) {
        setSelectedId(null);
        setDetail(null);
      }
      onChanged();
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="space-y-1">
          <Label htmlFor="budget-domain-filter">Домен</Label>
          <select
            id="budget-domain-filter"
            className="h-9 rounded-md border px-3 text-sm"
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value as BudgetDomain | "")}
          >
            <option value="">Все домены</option>
            {BUDGET_DOMAINS.map((d) => (
              <option key={d} value={d}>
                {BUDGET_DOMAIN_LABELS[d]}
              </option>
            ))}
          </select>
        </div>
        <Can permission={PERMISSIONS.BUDGET_MANAGE}>
          <BudgetFormDialog trigger={<Button>Новый бюджет</Button>} onSubmitted={onChanged} />
        </Can>
      </div>

      <ErrorState error={listError ?? undefined} onRetry={fetchList} />
      {listLoading ? <LoadingScreen label="Загрузка бюджетов" /> : null}

      {!listLoading && !listError && items.length === 0 ? (
        <EmptyState title="Бюджетов нет" description="Создайте первый бюджет." />
      ) : null}

      {!listLoading && !listError && items.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-4">Название</th>
                <th className="py-2 pr-4">Домен</th>
                <th className="py-2 pr-4">Период</th>
                <th className="py-2 pr-4">План</th>
                <th className="py-2">Действия</th>
              </tr>
            </thead>
            <tbody>
              {items.map((budget) => (
                <tr key={budget.id} className="border-b last:border-0">
                  <td className="py-2 pr-4">{budget.name}</td>
                  <td className="py-2 pr-4">{BUDGET_DOMAIN_LABELS[budget.domain]}</td>
                  <td className="py-2 pr-4">
                    {budget.period_start} – {budget.period_end}
                  </td>
                  <td className="py-2 pr-4">{formatRub(budget.planned_amount)}</td>
                  <td className="py-2">
                    <div className="flex flex-wrap gap-1">
                      <Button size="sm" variant="outline" onClick={() => openBudget(budget.id)}>
                        Открыть
                      </Button>
                      <Can permission={PERMISSIONS.BUDGET_MANAGE}>
                        <BudgetFormDialog
                          trigger={
                            <Button size="sm" variant="outline">
                              Изменить
                            </Button>
                          }
                          initialData={budget}
                          onSubmitted={afterMutation}
                        />
                        <Button size="sm" variant="destructive" onClick={() => void removeBudget(budget)}>
                          Удалить
                        </Button>
                      </Can>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {selectedId ? (
        <Card>
          <CardHeader>
            <CardTitle>Детали бюджета</CardTitle>
          </CardHeader>
          <CardContent>
            {detailError ? <ErrorState error={detailError} onRetry={() => openBudget(selectedId)} /> : null}
            {detailLoading ? <LoadingScreen label="Загрузка бюджета" /> : null}
            {!detailLoading && !detailError && detail ? (
              <div className="space-y-3">
                <div className="grid gap-2 text-sm md:grid-cols-4">
                  <div>
                    <span className="text-muted-foreground">План:</span> {formatRub(detail.planned_amount)}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Факт:</span> {formatRub(detail.actual_total)}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Остаток:</span>{" "}
                    <span className={detail.remaining < 0 ? "font-semibold text-destructive" : ""}>
                      {formatRub(detail.remaining)}
                    </span>
                  </div>
                  <div data-testid="budget-detail-expense-count">
                    <span className="text-muted-foreground">Записей расходов:</span> {detail.expense_count}
                  </div>
                </div>
                {detail.by_article.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Расходов пока нет.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-muted-foreground">
                          <th className="py-2 pr-4">Статья</th>
                          <th className="py-2">Сумма</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.by_article.map((row) => (
                          <tr key={row.article_id ?? "none"} className="border-b last:border-0">
                            <td className="py-2 pr-4">{row.article_name}</td>
                            <td className="py-2">{formatRub(row.amount)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
};
