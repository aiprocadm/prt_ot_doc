import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { budgetApi } from "@/api/budget";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { BREAKDOWN_DIMENSION_LABELS, BUDGET_DOMAIN_LABELS, formatRub } from "@/pages/budget/budgetVocab";
import type { BreakdownDimension, BudgetBreakdownDto, BudgetOverviewDto } from "@/types/dto/budget";

const DIMENSIONS: BreakdownDimension[] = ["article", "domain", "company", "branch", "site"];

interface Props {
  overview: BudgetOverviewDto;
  onWindowChange: (range: { date_from: string; date_to: string }) => void;
}

export const OverviewTab = ({ overview, onWindowChange }: Props) => {
  const [dateFrom, setDateFrom] = useState(overview.date_from);
  const [dateTo, setDateTo] = useState(overview.date_to);
  const [dimension, setDimension] = useState<BreakdownDimension>("article");

  // Синхронизируем поля периода с фактическим окном, применённым бэкендом
  // (после «Применить» страница перезагружает overview — оба bound приходят обратно).
  useEffect(() => {
    setDateFrom(overview.date_from);
    setDateTo(overview.date_to);
  }, [overview.date_from, overview.date_to]);

  const breakdownLoader = useCallback(
    () => budgetApi.getBreakdown({ dimension, date_from: overview.date_from, date_to: overview.date_to }),
    [dimension, overview.date_from, overview.date_to]
  );
  const breakdownRes = useAsyncResource<BudgetBreakdownDto | null>({
    loader: breakdownLoader,
    initialData: null,
    errorMessage: "Не удалось загрузить разрез бюджета"
  });

  // Пустая граница ушла бы на бэкенд как date_from="" (axios отбрасывает только null/undefined)
  // и вернулась бы 422 с голым тостом — поэтому «Применить» блокируется, пока обе даты не заданы.
  const windowComplete = Boolean(dateFrom && dateTo);

  const applyWindow = () => {
    if (!windowComplete) return;
    // Оба bound отправляются всегда: бэкенд по умолчанию берёт текущий календарный
    // год для каждой границы независимо, и одиночная граница может дать инвертированное
    // окно (422).
    onWindowChange({ date_from: dateFrom, date_to: dateTo });
  };

  const breakdown = breakdownRes.data;
  const maxAmount = Math.max(1, ...(breakdown?.items.map((item) => item.amount) ?? [1]));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Период</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label htmlFor="budget-overview-from">С</Label>
              <Input
                id="budget-overview-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="budget-overview-to">По</Label>
              <Input id="budget-overview-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <Button onClick={applyWindow} disabled={!windowComplete}>
              Применить
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {overview.domains.map((domain) => (
          <Card key={domain.domain} data-testid={`budget-domain-card-${domain.domain}`}>
            <CardHeader className="space-y-2">
              <CardTitle className="text-base">{BUDGET_DOMAIN_LABELS[domain.domain]}</CardTitle>
              {domain.read_only ? <Badge variant="secondary">ведётся на складе</Badge> : null}
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">План</span>
                  <span>{formatRub(domain.planned)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Факт</span>
                  <span>{formatRub(domain.actual)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Остаток</span>
                  <span className={domain.remaining < 0 ? "font-semibold text-destructive" : ""}>
                    {formatRub(domain.remaining)}
                  </span>
                </div>
              </div>

              {domain.read_only ? (
                <div className="space-y-2">
                  {(domain.warning_unpriced_receipts ?? 0) > 0 ? (
                    <p className="text-xs text-amber-600">Приходов без цены: {domain.warning_unpriced_receipts}</p>
                  ) : null}
                  <Button asChild variant="outline" size="sm">
                    <Link to="/warehouse">Открыть склад</Link>
                  </Button>
                </div>
              ) : null}

              {domain.budgets.length === 0 ? (
                <p className="text-xs text-muted-foreground">Бюджеты не заданы</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-muted-foreground">
                        <th className="py-1 pr-2">Бюджет</th>
                        <th className="py-1 pr-2">Период</th>
                        <th className="py-1 pr-2">План</th>
                        <th className="py-1 pr-2">Факт за период</th>
                        <th className="py-1">Остаток</th>
                      </tr>
                    </thead>
                    <tbody>
                      {domain.budgets.map((budget) => (
                        <tr key={budget.id} className="border-t">
                          <td className="py-1 pr-2">{budget.name}</td>
                          <td className="py-1 pr-2">
                            {budget.period_start} – {budget.period_end}
                          </td>
                          <td className="py-1 pr-2">{formatRub(budget.planned_amount)}</td>
                          <td className="py-1 pr-2">{formatRub(budget.actual_own_period)}</td>
                          <td className={`py-1 ${budget.remaining < 0 ? "font-semibold text-destructive" : ""}`}>
                            {formatRub(budget.remaining)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Разрез</CardTitle>
            <div className="flex flex-wrap gap-1">
              {DIMENSIONS.map((d) => (
                <Button
                  key={d}
                  size="sm"
                  variant={dimension === d ? "default" : "outline"}
                  aria-pressed={dimension === d}
                  onClick={() => setDimension(d)}
                >
                  {BREAKDOWN_DIMENSION_LABELS[d]}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {breakdownRes.error ? (
            <ErrorState error={breakdownRes.error} onRetry={() => void breakdownRes.reload().catch(() => undefined)} />
          ) : breakdownRes.loading && !breakdown ? (
            <p className="py-6 text-center text-sm text-muted-foreground" role="status">
              Загрузка разреза...
            </p>
          ) : !breakdown || breakdown.items.length === 0 ? (
            <EmptyState title="Нет данных" description="В этом разрезе пока пусто." />
          ) : (
            // При смене разреза таблица гасится и помечается aria-busy, иначе устаревшие
            // строки молча висели бы как актуальные до прихода ответа.
            <div
              className={`overflow-x-auto transition-opacity ${breakdownRes.loading ? "opacity-50" : ""}`}
              aria-busy={breakdownRes.loading}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4">Название</th>
                    <th className="py-2">Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  {breakdown.items.map((item) => (
                    <tr key={item.id || item.name} className="border-b last:border-0">
                      <td className="py-2 pr-4">{item.name}</td>
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <span className="w-28 shrink-0 text-right">{formatRub(item.amount)}</span>
                          <div className="h-2 flex-1 rounded bg-muted">
                            <div
                              className="h-2 rounded bg-primary"
                              style={{ width: `${(item.amount / maxAmount) * 100}%` }}
                            />
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="pt-2 text-xs text-muted-foreground">СИЗ-закупки в разрезе не участвуют.</p>
        </CardContent>
      </Card>
    </div>
  );
};
