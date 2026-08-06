import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { budgetApi } from "@/api/budget";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ReimbursementFormDialog } from "@/features/budget/ReimbursementFormDialog";
import {
  BUDGET_DOMAIN_LABELS,
  REIMBURSEMENT_STATUS_LABELS,
  REIMBURSEMENT_STATUSES,
  formatRub,
  toApiError,
} from "@/pages/budget/budgetVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ApiError } from "@/types/dto/common";
import type {
  BudgetExpensePageDto,
  BudgetReimbursementDetailDto,
  BudgetReimbursementDto,
  BudgetReimbursementPageDto,
  BudgetReimbursementStatus,
} from "@/types/dto/budget";

type ReimbursementAction = "submit" | "approve" | "reject" | "pay";

/**
 * Разрешённые переходы FSM (тот же паттерн, что ACTIONS_BY_STATUS в WorkPermitDetailPage):
 * терминальные rejected/paid действий не предлагают вовсе.
 */
const ACTIONS_BY_STATUS: Record<
  string,
  Array<{ name: ReimbursementAction; label: string }>
> = {
  draft: [{ name: "submit", label: "Подать" }],
  submitted: [
    { name: "approve", label: "Одобрить" },
    { name: "reject", label: "Отклонить" },
  ],
  approved: [{ name: "pay", label: "Выплатить" }],
};

/** Решение (approve/reject) требует ввода — собираем его отдельным маленьким диалогом. */
interface DecisionState {
  reimbursement: BudgetReimbursementDto;
  action: "approve" | "reject";
}

interface Props {
  reimbursements: BudgetReimbursementPageDto;
  expenses: BudgetExpensePageDto;
  onChanged: () => void;
}

export const ReimbursementsTab = ({
  reimbursements,
  expenses,
  onChanged,
}: Props) => {
  const [statusFilter, setStatusFilter] = useState<
    BudgetReimbursementStatus | ""
  >("");
  const [items, setItems] = useState<BudgetReimbursementDto[]>(
    reimbursements.items,
  );
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<ApiError | null>(null);
  const requestSeq = useRef(0);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<BudgetReimbursementDetailDto | null>(
    null,
  );
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<ApiError | null>(null);

  const [expenseToAttach, setExpenseToAttach] = useState("");
  const [decision, setDecision] = useState<DecisionState | null>(null);
  const [approvedAmount, setApprovedAmount] = useState("");
  const [decisionReason, setDecisionReason] = useState("");
  const [decisionSubmitting, setDecisionSubmitting] = useState(false);

  // Без фильтра — источник истины это props (страница уже загрузила полный список).
  // С фильтром — свой запрос budgetApi.listReimbursements({status}); перезапускается и при
  // смене фильтра, и при обновлении reimbursements сверху (после onChanged), чтобы фильтр
  // не «слетал» после создания/действия/удаления заявки.
  const fetchList = useCallback(() => {
    if (!statusFilter) {
      // Инвалидируем незавершённый отфильтрованный запрос: без bump'а его .then() прошёл бы
      // проверку seq и перезаписал только что выставленный полный список.
      requestSeq.current += 1;
      setItems(reimbursements.items);
      setListError(null);
      setListLoading(false);
      return;
    }
    const seq = ++requestSeq.current;
    setListLoading(true);
    setListError(null);
    budgetApi
      .listReimbursements({ status: statusFilter })
      .then((page) => {
        if (seq === requestSeq.current) setItems(page.items);
      })
      .catch((err) => {
        if (seq === requestSeq.current)
          setListError(toApiError(err, "Не удалось загрузить заявки"));
      })
      .finally(() => {
        if (seq === requestSeq.current) setListLoading(false);
      });
  }, [statusFilter, reimbursements]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const openReimbursement = useCallback((id: string) => {
    setSelectedId(id);
    setDetail(null);
    setDetailLoading(true);
    setDetailError(null);
    setExpenseToAttach("");
    budgetApi
      .getReimbursement(id)
      .then(setDetail)
      .catch((err) =>
        setDetailError(toApiError(err, "Не удалось загрузить заявку")),
      )
      .finally(() => setDetailLoading(false));
  }, []);

  const afterMutation = () => {
    onChanged();
    if (selectedId) openReimbursement(selectedId);
  };

  const removeReimbursement = async (reimbursement: BudgetReimbursementDto) => {
    if (!window.confirm(`Удалить заявку «${reimbursement.title}»?`)) return;
    try {
      await budgetApi.deleteReimbursement(reimbursement.id);
      if (selectedId === reimbursement.id) {
        setSelectedId(null);
        setDetail(null);
      }
      onChanged();
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  const runAction = async (
    reimbursement: BudgetReimbursementDto,
    name: ReimbursementAction,
  ) => {
    // approve/reject требуют ввода (сумма / причина) — уходим в диалог решения.
    if (name === "approve" || name === "reject") {
      setDecision({ reimbursement, action: name });
      setApprovedAmount(
        name === "approve" ? String(reimbursement.requested_amount) : "",
      );
      setDecisionReason("");
      return;
    }
    try {
      await budgetApi.reimbursementAction(reimbursement.id, name);
      afterMutation();
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  const submitDecision = async () => {
    if (!decision) return;
    const body: { approved_amount?: number; decision_reason?: string } = {};
    if (decision.action === "approve") {
      // approved_amount опционален (по умолчанию = requested), но если введён — должен быть
      // числом и не больше запрошенного: 422 approved_amount_invalid ловим до запроса.
      if (approvedAmount.trim() !== "") {
        const amount = Number(approvedAmount);
        if (!Number.isFinite(amount) || amount <= 0) {
          toast.error("Укажите корректную одобренную сумму");
          return;
        }
        if (amount > decision.reimbursement.requested_amount) {
          toast.error("Одобренная сумма не может превышать запрашиваемую");
          return;
        }
        body.approved_amount = amount;
      }
    } else {
      // Бэкенд отдаёт 422 decision_reason_required — не даём пустой причине уйти в сеть.
      if (!decisionReason.trim()) {
        toast.error("Укажите причину отклонения");
        return;
      }
      body.decision_reason = decisionReason.trim();
    }
    setDecisionSubmitting(true);
    try {
      await budgetApi.reimbursementAction(
        decision.reimbursement.id,
        decision.action,
        body,
      );
      toast.success(
        decision.action === "approve" ? "Заявка одобрена" : "Заявка отклонена",
      );
      setDecision(null);
      afterMutation();
    } catch (err) {
      toast.error(
        (err as { message?: string })?.message ??
          "Не удалось выполнить действие",
      );
    } finally {
      setDecisionSubmitting(false);
    }
  };

  const attachExpense = async () => {
    if (!selectedId || !expenseToAttach) {
      toast.error("Выберите расход");
      return;
    }
    try {
      await budgetApi.addReimbursementItem(selectedId, expenseToAttach);
      setExpenseToAttach("");
      afterMutation();
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  const detachExpense = async (expenseId: string) => {
    if (!selectedId) return;
    try {
      await budgetApi.removeReimbursementItem(selectedId, expenseId);
      afterMutation();
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  // Прикреплять предлагаем только ещё не связанные расходы из уже загруженного страницей списка.
  const linkedIds = new Set(
    (detail?.items ?? []).map((item) => item.expense_id),
  );
  const attachableExpenses = expenses.items.filter(
    (expense) => !linkedIds.has(expense.id),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="space-y-1">
          <Label htmlFor="reimbursement-status-filter">Статус</Label>
          <select
            id="reimbursement-status-filter"
            className="h-9 rounded-md border px-3 text-sm"
            value={statusFilter}
            onChange={(e) =>
              setStatusFilter(e.target.value as BudgetReimbursementStatus | "")
            }
          >
            <option value="">Все статусы</option>
            {REIMBURSEMENT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {REIMBURSEMENT_STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
        <Can permission={PERMISSIONS.BUDGET_MANAGE}>
          <ReimbursementFormDialog
            trigger={<Button>Новая заявка</Button>}
            onSubmitted={onChanged}
          />
        </Can>
      </div>

      <ErrorState error={listError ?? undefined} onRetry={fetchList} />
      {listLoading ? <LoadingScreen label="Загрузка заявок" /> : null}

      {!listLoading && !listError && items.length === 0 ? (
        statusFilter ? (
          <EmptyState
            title="Ничего не найдено по фильтру"
            description="Измените или сбросьте фильтр."
          />
        ) : (
          <EmptyState
            title="Заявок нет"
            description="Создайте первую заявку на возмещение."
          />
        )
      ) : null}

      {!listLoading && !listError && items.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-4">Название</th>
                <th className="py-2 pr-4">Статус</th>
                <th className="py-2 pr-4">Период</th>
                <th className="py-2 pr-4">Запрошено</th>
                <th className="py-2 pr-4">Одобрено</th>
                <th className="py-2 pr-4">Расходов</th>
                <th className="py-2">Действия</th>
              </tr>
            </thead>
            <tbody>
              {items.map((reimbursement) => (
                <tr key={reimbursement.id} className="border-b last:border-0">
                  <td className="py-2 pr-4">{reimbursement.title}</td>
                  <td className="py-2 pr-4">
                    <StatusBadge status={reimbursement.status} />
                  </td>
                  <td className="py-2 pr-4">
                    {reimbursement.period_start} – {reimbursement.period_end}
                  </td>
                  <td className="py-2 pr-4">
                    {formatRub(reimbursement.requested_amount)}
                  </td>
                  <td className="py-2 pr-4">
                    {reimbursement.approved_amount === null
                      ? "—"
                      : formatRub(reimbursement.approved_amount)}
                  </td>
                  <td className="py-2 pr-4">{reimbursement.item_count}</td>
                  <td className="py-2">
                    <div className="flex flex-wrap gap-1">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openReimbursement(reimbursement.id)}
                      >
                        Открыть
                      </Button>
                      <Can permission={PERMISSIONS.BUDGET_MANAGE}>
                        {/* Правка и удаление разрешены бэкендом только в draft (иначе 409). */}
                        {reimbursement.status === "draft" ? (
                          <>
                            <ReimbursementFormDialog
                              trigger={
                                <Button size="sm" variant="outline">
                                  Изменить
                                </Button>
                              }
                              initialData={reimbursement}
                              onSubmitted={afterMutation}
                            />
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() =>
                                void removeReimbursement(reimbursement)
                              }
                            >
                              Удалить
                            </Button>
                          </>
                        ) : null}
                        {(ACTIONS_BY_STATUS[reimbursement.status] ?? []).map(
                          (a) => (
                            <Button
                              key={a.name}
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                void runAction(reimbursement, a.name)
                              }
                            >
                              {a.label}
                            </Button>
                          ),
                        )}
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
            <CardTitle>Детали заявки</CardTitle>
          </CardHeader>
          <CardContent>
            {detailError ? (
              <ErrorState
                error={detailError}
                onRetry={() => openReimbursement(selectedId)}
              />
            ) : null}
            {detailLoading ? <LoadingScreen label="Загрузка заявки" /> : null}
            {!detailLoading && !detailError && detail ? (
              <div className="space-y-3">
                <div className="grid gap-2 text-sm md:grid-cols-4">
                  <div>
                    <span className="text-muted-foreground">Запрошено:</span>{" "}
                    {formatRub(detail.requested_amount)}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Одобрено:</span>{" "}
                    {detail.approved_amount === null
                      ? "—"
                      : formatRub(detail.approved_amount)}
                  </div>
                  <div>
                    <span className="text-muted-foreground">
                      Сумма расходов:
                    </span>{" "}
                    {formatRub(detail.items_amount)}
                  </div>
                  <div data-testid="reimbursement-detail-item-count">
                    <span className="text-muted-foreground">
                      Записей расходов:
                    </span>{" "}
                    {detail.item_count}
                  </div>
                </div>
                {detail.reference ? (
                  <p className="text-sm">
                    <span className="text-muted-foreground">Номер в СФР:</span>{" "}
                    {detail.reference}
                  </p>
                ) : null}
                {detail.decision_reason ? (
                  <p className="text-sm">
                    <span className="text-muted-foreground">
                      Причина решения:
                    </span>{" "}
                    {detail.decision_reason}
                  </p>
                ) : null}

                {detail.status === "draft" ? (
                  <Can permission={PERMISSIONS.BUDGET_MANAGE}>
                    <div className="flex flex-wrap items-end gap-2">
                      <div className="space-y-1">
                        <Label htmlFor="reimbursement-attach-expense">
                          Добавить расход
                        </Label>
                        <select
                          id="reimbursement-attach-expense"
                          className="h-9 rounded-md border px-3 text-sm"
                          value={expenseToAttach}
                          onChange={(e) => setExpenseToAttach(e.target.value)}
                        >
                          <option value="">Выберите расход</option>
                          {attachableExpenses.map((expense) => (
                            <option key={expense.id} value={expense.id}>
                              {expense.title} ({expense.occurred_on})
                            </option>
                          ))}
                        </select>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void attachExpense()}
                      >
                        Добавить
                      </Button>
                    </div>
                  </Can>
                ) : null}

                {detail.items.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Расходов в заявке пока нет.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-muted-foreground">
                          <th className="py-2 pr-4">Дата</th>
                          <th className="py-2 pr-4">Название</th>
                          <th className="py-2 pr-4">Домен</th>
                          <th className="py-2 pr-4">Сумма</th>
                          <th className="py-2">Действия</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.items.map((item) => (
                          <tr
                            key={item.expense_id}
                            className="border-b last:border-0"
                          >
                            <td className="py-2 pr-4">{item.occurred_on}</td>
                            <td className="py-2 pr-4">{item.title}</td>
                            <td className="py-2 pr-4">
                              {BUDGET_DOMAIN_LABELS[item.domain]}
                            </td>
                            <td className="py-2 pr-4">
                              {formatRub(item.amount)}
                            </td>
                            <td className="py-2">
                              {detail.status === "draft" ? (
                                <Can permission={PERMISSIONS.BUDGET_MANAGE}>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() =>
                                      void detachExpense(item.expense_id)
                                    }
                                  >
                                    Убрать
                                  </Button>
                                </Can>
                              ) : null}
                            </td>
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

      <Dialog
        open={decision !== null}
        onOpenChange={(next) => (next ? undefined : setDecision(null))}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {decision?.action === "approve"
                ? "Одобрить заявку"
                : "Отклонить заявку"}
            </DialogTitle>
            <DialogDescription>
              {decision?.action === "approve"
                ? "Одобренная сумма по умолчанию равна запрашиваемой и не может её превышать."
                : "Укажите причину отклонения — она обязательна."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {decision?.action === "approve" ? (
              <div className="space-y-2">
                <Label htmlFor="r-approved-amount">Одобренная сумма</Label>
                <Input
                  id="r-approved-amount"
                  type="number"
                  value={approvedAmount}
                  onChange={(e) => setApprovedAmount(e.target.value)}
                />
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="r-decision-reason">Причина отклонения</Label>
                <Textarea
                  id="r-decision-reason"
                  value={decisionReason}
                  onChange={(e) => setDecisionReason(e.target.value)}
                />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              onClick={() => void submitDecision()}
              disabled={decisionSubmitting}
            >
              {decisionSubmitting ? "Сохранение..." : "Подтвердить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
