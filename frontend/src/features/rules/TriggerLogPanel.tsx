import { useCallback, useState } from "react";

import { rulesApi } from "@/api/rules";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import {
  ACTION_LABELS,
  OUTCOME_LABELS,
  STATUS_LABELS,
  eventLabel,
} from "@/pages/rules/rulesVocab";
import type {
  AutomationRuleRead,
  RuleActionType,
  TriggerRead,
  TriggerStatus,
} from "@/types/dto/rules";

interface Props {
  rules: AutomationRuleRead[];
}

const STATUS_BADGE_VARIANT: Record<
  TriggerStatus,
  "secondary" | "outline" | "destructive"
> = {
  success: "secondary",
  partial: "outline",
  error: "destructive",
};

const formatResults = (trigger: TriggerRead): string =>
  trigger.actions_result
    .map((entry) => {
      const type = String(entry.type ?? "");
      const outcome = String(entry.outcome ?? "");
      return `${ACTION_LABELS[type as RuleActionType] ?? type}: ${OUTCOME_LABELS[outcome] ?? outcome}`;
    })
    .join(", ");

export const TriggerLogPanel = ({ rules }: Props) => {
  const [ruleFilter, setRuleFilter] = useState("");

  const loader = useCallback(
    () =>
      rulesApi
        .triggers(ruleFilter ? { rule_id: ruleFilter } : {})
        .then((page) => page.items),
    [ruleFilter],
  );
  const { data, loading, error, reload } = useAsyncResource<TriggerRead[]>({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить журнал срабатываний",
  });

  const ruleName = (ruleId: string): string =>
    rules.find((r) => r.id === ruleId)?.name ?? ruleId;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Журнал срабатываний</CardTitle>
        <CardDescription>
          Последние срабатывания правил и результаты действий.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Фильтр по правилу"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={ruleFilter}
            onChange={(e) => setRuleFilter(e.target.value)}
          >
            <option value="">Все правила</option>
            {rules.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void reload().catch(() => undefined)}
          >
            Обновить
          </Button>
        </div>
        <ErrorState
          error={error ?? undefined}
          onRetry={() => void reload().catch(() => undefined)}
        />
        {loading ? <LoadingScreen label="Загрузка журнала" /> : null}
        {!loading && !error && data.length === 0 ? (
          <EmptyState
            title="Срабатываний нет"
            description="Правила ещё не срабатывали или фильтр пуст."
          />
        ) : null}
        {!loading && !error && data.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-4">Время</th>
                  <th className="py-2 pr-4">Правило</th>
                  <th className="py-2 pr-4">Событие</th>
                  <th className="py-2 pr-4">Статус</th>
                  <th className="py-2">Результаты</th>
                </tr>
              </thead>
              <tbody>
                {data.map((trigger) => (
                  <tr key={trigger.id} className="border-b last:border-0">
                    <td className="py-2 pr-4 whitespace-nowrap">
                      {new Date(trigger.created_at).toLocaleString("ru-RU")}
                    </td>
                    <td className="py-2 pr-4">{ruleName(trigger.rule_id)}</td>
                    <td className="py-2 pr-4">
                      {eventLabel(trigger.event_type)}
                    </td>
                    <td className="py-2 pr-4">
                      <Badge variant={STATUS_BADGE_VARIANT[trigger.status]}>
                        {STATUS_LABELS[trigger.status]}
                      </Badge>
                    </td>
                    <td className="py-2">{formatResults(trigger) || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};
