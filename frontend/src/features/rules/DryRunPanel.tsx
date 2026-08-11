import { useState } from "react";

import { rulesApi } from "@/api/rules";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { OP_LABELS, eventLabel } from "@/pages/rules/rulesVocab";
import type { AutomationRuleRead, DryRunOut, EventTypeMeta, RuleConditionOp } from "@/types/dto/rules";

interface Props {
  eventTypes: EventTypeMeta[];
  rules: AutomationRuleRead[];
}

const formatValue = (value: unknown): string => {
  if (value === undefined || value === null) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
};

export const DryRunPanel = ({ eventTypes, rules }: Props) => {
  const [ruleId, setRuleId] = useState("");
  const [eventType, setEventType] = useState("");
  const [payloadText, setPayloadText] = useState("{}");
  const [result, setResult] = useState<DryRunOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const payloadSkeleton = (code: string): string => {
    const meta = eventTypes.find((e) => e.event_type === code);
    const skeleton = Object.fromEntries((meta?.fields ?? []).map((f) => [f.name, null]));
    return JSON.stringify(skeleton, null, 2);
  };

  const onRuleChange = (id: string) => {
    setRuleId(id);
    setResult(null);
    setError(null);
    const rule = rules.find((r) => r.id === id);
    if (rule) {
      // По умолчанию проверяем на событии самого правила.
      setEventType(rule.event_type);
      setPayloadText(payloadSkeleton(rule.event_type));
    }
  };

  const onEventChange = (code: string) => {
    setEventType(code);
    setResult(null);
    setError(null);
    if (code) setPayloadText(payloadSkeleton(code));
  };

  const run = async () => {
    const rule = rules.find((r) => r.id === ruleId);
    if (!rule || !eventType) {
      setError("Выберите правило и событие");
      return;
    }
    let payload: unknown;
    try {
      payload = JSON.parse(payloadText || "{}");
    } catch {
      setError("Некорректный JSON в payload события");
      return;
    }
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
      setError("Payload должен быть JSON-объектом");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      setResult(
        await rulesApi.dryRun({
          rule: {
            name: rule.name,
            description: rule.description,
            event_type: rule.event_type,
            conditions_json: rule.conditions_json,
            actions_json: rule.actions_json,
            priority: rule.priority,
            is_enabled: rule.is_enabled
          },
          event: { event_type: eventType, payload: payload as Record<string, unknown> }
        })
      );
    } catch {
      // Текст ошибки API уже показан глобальным обработчиком — тут только inline-статус.
      setResult(null);
      setError("Не удалось выполнить проверку");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Проверка правила (dry-run)</CardTitle>
        <CardDescription>
          Подставьте тестовый payload события и проверьте условия правила без выполнения действий.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="dry-run-rule">Правило</Label>
            <select
              id="dry-run-rule"
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={ruleId}
              onChange={(e) => onRuleChange(e.target.value)}
            >
              <option value="">— выберите правило —</option>
              {rules.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="dry-run-event">Событие</Label>
            <select
              id="dry-run-event"
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={eventType}
              onChange={(e) => onEventChange(e.target.value)}
            >
              <option value="">— выберите событие —</option>
              {eventTypes.map((e) => (
                <option key={e.event_type} value={e.event_type}>
                  {eventLabel(e.event_type)} ({e.event_type})
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="dry-run-payload">Payload события (JSON)</Label>
          <Textarea
            id="dry-run-payload"
            rows={6}
            className="font-mono text-xs"
            value={payloadText}
            onChange={(e) => setPayloadText(e.target.value)}
          />
        </div>
        <Button onClick={() => void run()} disabled={running}>
          {running ? "Проверяем..." : "Проверить"}
        </Button>
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        {result ? (
          <div className="space-y-3">
            <Badge variant={result.matched ? "default" : "secondary"}>
              {result.matched ? "Совпадает" : "Не совпадает"}
            </Badge>
            {result.condition_results.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4">Поле</th>
                      <th className="py-2 pr-4">Оператор</th>
                      <th className="py-2 pr-4">Ожидание</th>
                      <th className="py-2 pr-4">Факт</th>
                      <th className="py-2">Совпало</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.condition_results.map((cr, idx) => (
                      <tr key={idx} className="border-b last:border-0">
                        <td className="py-2 pr-4 font-mono text-xs">{cr.field}</td>
                        <td className="py-2 pr-4">{OP_LABELS[cr.op as RuleConditionOp] ?? cr.op}</td>
                        <td className="py-2 pr-4">{formatValue(cr.value)}</td>
                        <td className="py-2 pr-4">{formatValue(cr.actual)}</td>
                        <td className="py-2">{cr.matched ? "✓" : "✗"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Условий нет — правило срабатывает на любое событие этого типа.</p>
            )}
            {result.would_actions.length > 0 ? (
              <div className="space-y-1">
                <p className="text-sm font-medium">Будут выполнены действия:</p>
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {result.would_actions.map((a, idx) => (
                    <li key={idx}>{a}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};
