import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { rulesApi } from "@/api/rules";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ACTION_LABELS, OP_LABELS, eventLabel, kindLabel } from "@/pages/rules/rulesVocab";
import type {
  AutomationRuleCreate,
  AutomationRuleRead,
  EventTypeMeta,
  RuleAction,
  RuleActionType,
  RuleCondition,
  RuleConditionOp
} from "@/types/dto/rules";

interface Props {
  trigger: ReactNode;
  eventTypes: EventTypeMeta[];
  initialData?: AutomationRuleRead;
  onSubmitted?: () => void;
}

/** Строка условия в форме: value всегда строкой, коэрсия по kind — на submit. */
type ConditionRow = { field: string; op: RuleConditionOp; value: string };

/** Плоская форма действия: для каждого типа используется своё подмножество полей. */
type ActionRow = {
  type: RuleActionType;
  title_template: string;
  description_template: string;
  priority: string;
  due_in_days: string;
  assignee_mode: "none" | "actor" | "user_id";
  recipient_mode: "actor" | "user_id" | "role";
  user_id: string;
  roles: string[];
  body_template: string;
};

const TASK_PRIORITY_OPTIONS: Array<[string, string]> = [
  ["low", "Низкий"],
  ["medium", "Средний"],
  ["high", "Высокий"],
  ["critical", "Критический"]
];

const ROLE_OPTIONS: Array<[string, string]> = [
  ["admin", "Администратор"],
  ["owner", "Владелец"],
  ["ot_specialist", "Специалист по ОТ"],
  ["line_manager", "Линейный руководитель"],
  ["hr", "HR"]
];

const emptyAction = (): ActionRow => ({
  type: "create_task",
  title_template: "",
  description_template: "",
  priority: "medium",
  due_in_days: "",
  assignee_mode: "none",
  recipient_mode: "actor",
  user_id: "",
  roles: [],
  body_template: ""
});

const conditionValueToString = (value: unknown): string => {
  if (value === undefined || value === null) return "";
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
};

const toConditionRows = (rule: AutomationRuleRead): ConditionRow[] =>
  (rule.conditions_json.conditions ?? []).map((c) => ({
    field: c.field,
    op: c.op,
    value: conditionValueToString(c.value)
  }));

const toActionRows = (rule: AutomationRuleRead): ActionRow[] =>
  rule.actions_json.map((a) => ({
    ...emptyAction(),
    type: a.type,
    title_template: typeof a.title_template === "string" ? a.title_template : "",
    description_template: typeof a.description_template === "string" ? a.description_template : "",
    priority: typeof a.priority === "string" ? a.priority : "medium",
    due_in_days: a.due_in_days === undefined || a.due_in_days === null ? "" : String(a.due_in_days),
    assignee_mode: (a.assignee_mode as ActionRow["assignee_mode"]) ?? "none",
    recipient_mode: (a.recipient_mode as ActionRow["recipient_mode"]) ?? "actor",
    user_id: typeof a.user_id === "string" ? a.user_id : "",
    roles: Array.isArray(a.roles) ? a.roles.map(String) : [],
    body_template: typeof a.body_template === "string" ? a.body_template : ""
  }));

export const RuleFormDialog = ({ trigger, eventTypes, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("100");
  const [eventType, setEventType] = useState("");
  const [match, setMatch] = useState<"all" | "any">("all");
  const [conditions, setConditions] = useState<ConditionRow[]>([]);
  const [actions, setActions] = useState<ActionRow[]>([]);
  const isEdit = Boolean(initialData);

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      setName(initialData.name);
      setDescription(initialData.description ?? "");
      setPriority(String(initialData.priority));
      setEventType(initialData.event_type);
      setMatch(initialData.conditions_json.match === "any" ? "any" : "all");
      setConditions(toConditionRows(initialData));
      setActions(toActionRows(initialData));
    } else {
      setName("");
      setDescription("");
      setPriority("100");
      setEventType("");
      setMatch("all");
      setConditions([]);
      setActions([]);
    }
  }, [open, initialData]);

  const selectedEvent = eventTypes.find((e) => e.event_type === eventType);
  const fieldKind = (fieldName: string): string =>
    selectedEvent?.fields.find((f) => f.name === fieldName)?.kind ?? "string";

  const onEventChange = (next: string) => {
    setEventType(next);
    // Поля условий привязаны к каталогу события — при смене события условия сбрасываются.
    setConditions([]);
  };

  const setCondition = (idx: number, patch: Partial<ConditionRow>) =>
    setConditions((prev) => prev.map((row, i) => (i === idx ? { ...row, ...patch } : row)));

  const setAction = (idx: number, patch: Partial<ActionRow>) =>
    setActions((prev) => prev.map((row, i) => (i === idx ? { ...row, ...patch } : row)));

  const buildConditions = (): RuleCondition[] => {
    const built: RuleCondition[] = [];
    for (const row of conditions) {
      if (!row.field) continue;
      if (row.op === "exists") {
        // Пустое значение трактуем как true — селект в этом случае показывает «да».
        built.push({ field: row.field, op: row.op, value: row.value !== "false" });
        continue;
      }
      const raw = row.value.trim();
      if (row.op === "in" || row.op === "not_in") {
        const parts = raw
          .split(",")
          .map((v) => v.trim())
          .filter(Boolean);
        built.push({
          field: row.field,
          op: row.op,
          value: fieldKind(row.field) === "number" ? parts.map(Number) : parts
        });
        continue;
      }
      if (raw === "") {
        // Пустая строка → value не отправляем (НЕ Number("") === 0).
        built.push({ field: row.field, op: row.op });
        continue;
      }
      built.push({
        field: row.field,
        op: row.op,
        value: fieldKind(row.field) === "number" ? Number(raw) : raw
      });
    }
    return built;
  };

  const buildActions = (): RuleAction[] =>
    actions.map((row) => {
      if (row.type === "create_task") {
        const action: RuleAction = {
          type: "create_task",
          title_template: row.title_template.trim(),
          priority: row.priority,
          assignee_mode: row.assignee_mode
        };
        if (row.description_template.trim()) action.description_template = row.description_template.trim();
        if (row.due_in_days.trim() !== "") action.due_in_days = Number.parseInt(row.due_in_days, 10);
        if (row.assignee_mode === "user_id") action.user_id = row.user_id.trim();
        return action;
      }
      if (row.type === "notify") {
        const action: RuleAction = {
          type: "notify",
          recipient_mode: row.recipient_mode,
          title_template: row.title_template.trim(),
          body_template: row.body_template.trim()
        };
        if (row.recipient_mode === "user_id") action.user_id = row.user_id.trim();
        if (row.recipient_mode === "role") action.roles = row.roles;
        return action;
      }
      return { type: "webhook" };
    });

  const onSubmit = async () => {
    if (!name.trim()) {
      toast.error("Укажите имя правила");
      return;
    }
    if (!eventType) {
      toast.error("Выберите событие");
      return;
    }
    if (actions.length === 0) {
      toast.error("Добавьте хотя бы одно действие");
      return;
    }
    const parsedPriority = Number.parseInt(priority, 10);
    setSubmitting(true);
    try {
      const payload: AutomationRuleCreate = {
        name: name.trim(),
        description: description.trim() || null,
        event_type: eventType,
        conditions_json: { match, conditions: buildConditions() },
        actions_json: buildActions(),
        priority: Number.isFinite(parsedPriority) ? parsedPriority : 100,
        is_enabled: initialData?.is_enabled ?? true
      };
      if (initialData) {
        await rulesApi.update(initialData.id, payload);
      } else {
        await rulesApi.create(payload);
      }
      toast.success(isEdit ? "Правило обновлено" : "Правило создано");
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      const error = err as { status?: number; message?: string };
      if (error?.status === 409) {
        toast.error("Имя уже занято");
      } else {
        toast.error(error?.message ?? "Не удалось сохранить правило");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать правило" : "Новое правило"}</DialogTitle>
          <DialogDescription>Событие, условия срабатывания и автоматические действия.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="rule-name">Имя</Label>
              <Input id="rule-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rule-priority">Приоритет</Label>
              <Input
                id="rule-priority"
                type="number"
                min={0}
                max={10000}
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="rule-description">Описание</Label>
            <Textarea
              id="rule-description"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="rule-event">Событие</Label>
            <select
              id="rule-event"
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
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

          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Label>Условия</Label>
              <select
                aria-label="Совпадение условий"
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={match}
                onChange={(e) => setMatch(e.target.value as "all" | "any")}
              >
                <option value="all">все условия</option>
                <option value="any">любое условие</option>
              </select>
              <Button
                size="sm"
                variant="outline"
                disabled={!selectedEvent}
                onClick={() =>
                  setConditions((prev) => [
                    ...prev,
                    { field: selectedEvent?.fields[0]?.name ?? "", op: "eq", value: "" }
                  ])
                }
              >
                Добавить условие
              </Button>
            </div>
            {!selectedEvent && conditions.length === 0 ? (
              <p className="text-xs text-muted-foreground">Выберите событие, чтобы добавить условия. Без условий правило срабатывает на все события.</p>
            ) : null}
            {conditions.map((row, idx) => (
              <div key={idx} data-testid={`cond-row-${idx}`} className="flex flex-wrap items-end gap-2">
                <div className="space-y-1">
                  <Label htmlFor={`rule-cond-field-${idx}`}>Поле</Label>
                  <select
                    id={`rule-cond-field-${idx}`}
                    aria-label="Поле"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={row.field}
                    onChange={(e) => setCondition(idx, { field: e.target.value, value: "" })}
                  >
                    {(selectedEvent?.fields ?? []).map((f) => (
                      <option key={f.name} value={f.name}>
                        {f.name} ({kindLabel(f.kind)})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor={`rule-cond-op-${idx}`}>Оператор</Label>
                  <select
                    id={`rule-cond-op-${idx}`}
                    aria-label="Оператор"
                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    value={row.op}
                    onChange={(e) => {
                      const nextOp = e.target.value as RuleConditionOp;
                      // Для exists стартовое значение "true" — иначе селект показывает «да»,
                      // а на submit ушло бы value: false.
                      setCondition(idx, { op: nextOp, value: nextOp === "exists" ? "true" : "" });
                    }}
                  >
                    {(Object.keys(OP_LABELS) as RuleConditionOp[]).map((op) => (
                      <option key={op} value={op}>
                        {OP_LABELS[op]}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor={`rule-cond-value-${idx}`}>Значение</Label>
                  {row.op === "exists" ? (
                    <select
                      id={`rule-cond-value-${idx}`}
                      aria-label="Значение"
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                      value={row.value || "true"}
                      onChange={(e) => setCondition(idx, { value: e.target.value })}
                    >
                      <option value="true">да</option>
                      <option value="false">нет</option>
                    </select>
                  ) : (
                    <Input
                      id={`rule-cond-value-${idx}`}
                      aria-label="Значение"
                      className="w-56"
                      placeholder={row.op === "in" || row.op === "not_in" ? "значения через запятую" : ""}
                      value={row.value}
                      onChange={(e) => setCondition(idx, { value: e.target.value })}
                    />
                  )}
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setConditions((prev) => prev.filter((_, i) => i !== idx))}
                >
                  Убрать
                </Button>
              </div>
            ))}
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label>Действия</Label>
              <Button size="sm" variant="outline" onClick={() => setActions((prev) => [...prev, emptyAction()])}>
                Добавить действие
              </Button>
            </div>
            {actions.map((row, idx) => (
              <div key={idx} data-testid={`action-card-${idx}`} className="space-y-3 rounded-md border p-3">
                <div className="flex flex-wrap items-end gap-2">
                  <div className="space-y-1">
                    <Label htmlFor={`rule-action-type-${idx}`}>Тип действия</Label>
                    <select
                      id={`rule-action-type-${idx}`}
                      aria-label="Тип действия"
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                      value={row.type}
                      onChange={(e) => setAction(idx, { type: e.target.value as RuleActionType })}
                    >
                      {(Object.keys(ACTION_LABELS) as RuleActionType[]).map((t) => (
                        <option key={t} value={t}>
                          {ACTION_LABELS[t]}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-auto"
                    onClick={() => setActions((prev) => prev.filter((_, i) => i !== idx))}
                  >
                    Убрать действие
                  </Button>
                </div>

                {row.type === "create_task" ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="space-y-1 md:col-span-2">
                      <Label htmlFor={`rule-action-title-${idx}`}>Заголовок задачи</Label>
                      <Input
                        id={`rule-action-title-${idx}`}
                        value={row.title_template}
                        onChange={(e) => setAction(idx, { title_template: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1 md:col-span-2">
                      <Label htmlFor={`rule-action-descr-${idx}`}>Описание задачи</Label>
                      <Textarea
                        id={`rule-action-descr-${idx}`}
                        rows={2}
                        value={row.description_template}
                        onChange={(e) => setAction(idx, { description_template: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor={`rule-action-priority-${idx}`}>Приоритет задачи</Label>
                      <select
                        id={`rule-action-priority-${idx}`}
                        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                        value={row.priority}
                        onChange={(e) => setAction(idx, { priority: e.target.value })}
                      >
                        {TASK_PRIORITY_OPTIONS.map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor={`rule-action-due-${idx}`}>Срок, дней</Label>
                      <Input
                        id={`rule-action-due-${idx}`}
                        type="number"
                        min={0}
                        max={365}
                        value={row.due_in_days}
                        onChange={(e) => setAction(idx, { due_in_days: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor={`rule-action-assignee-${idx}`}>Исполнитель</Label>
                      <select
                        id={`rule-action-assignee-${idx}`}
                        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                        value={row.assignee_mode}
                        onChange={(e) => setAction(idx, { assignee_mode: e.target.value as ActionRow["assignee_mode"] })}
                      >
                        <option value="none">Без исполнителя</option>
                        <option value="actor">Автор события</option>
                        <option value="user_id">Указать user ID</option>
                      </select>
                    </div>
                    {row.assignee_mode === "user_id" ? (
                      <div className="space-y-1">
                        <Label htmlFor={`rule-action-user-${idx}`}>User ID исполнителя</Label>
                        <Input
                          id={`rule-action-user-${idx}`}
                          value={row.user_id}
                          onChange={(e) => setAction(idx, { user_id: e.target.value })}
                        />
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {row.type === "notify" ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="space-y-1">
                      <Label htmlFor={`rule-action-recipient-${idx}`}>Получатель</Label>
                      <select
                        id={`rule-action-recipient-${idx}`}
                        className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                        value={row.recipient_mode}
                        onChange={(e) =>
                          setAction(idx, { recipient_mode: e.target.value as ActionRow["recipient_mode"] })
                        }
                      >
                        <option value="actor">Автор события</option>
                        <option value="user_id">Указать user ID</option>
                        <option value="role">По ролям</option>
                      </select>
                    </div>
                    {row.recipient_mode === "user_id" ? (
                      <div className="space-y-1">
                        <Label htmlFor={`rule-action-user-${idx}`}>User ID получателя</Label>
                        <Input
                          id={`rule-action-user-${idx}`}
                          value={row.user_id}
                          onChange={(e) => setAction(idx, { user_id: e.target.value })}
                        />
                      </div>
                    ) : null}
                    {row.recipient_mode === "role" ? (
                      <div className="space-y-1 md:col-span-2">
                        <Label>Роли</Label>
                        <div className="flex flex-wrap gap-3">
                          {ROLE_OPTIONS.map(([value, label]) => (
                            <label key={value} className="flex items-center gap-1 text-sm">
                              <input
                                type="checkbox"
                                aria-label={label}
                                checked={row.roles.includes(value)}
                                onChange={(e) =>
                                  setAction(idx, {
                                    roles: e.target.checked
                                      ? [...row.roles, value]
                                      : row.roles.filter((r) => r !== value)
                                  })
                                }
                              />
                              {label}
                            </label>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    <div className="space-y-1 md:col-span-2">
                      <Label htmlFor={`rule-action-title-${idx}`}>Заголовок уведомления</Label>
                      <Input
                        id={`rule-action-title-${idx}`}
                        value={row.title_template}
                        onChange={(e) => setAction(idx, { title_template: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1 md:col-span-2">
                      <Label htmlFor={`rule-action-body-${idx}`}>Текст уведомления</Label>
                      <Textarea
                        id={`rule-action-body-${idx}`}
                        rows={2}
                        value={row.body_template}
                        onChange={(e) => setAction(idx, { body_template: e.target.value })}
                      />
                    </div>
                  </div>
                ) : null}

                {row.type === "webhook" ? (
                  <p className="text-xs text-muted-foreground">
                    Отправит событие rule.triggered на webhook-подписки тенанта.
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => void onSubmit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
