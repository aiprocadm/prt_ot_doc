export type RuleConditionOp =
  | "eq"
  | "ne"
  | "in"
  | "not_in"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "contains"
  | "exists";

export type RuleActionType = "create_task" | "notify" | "webhook";

export type TriggerStatus = "success" | "partial" | "error";

export interface RuleCondition {
  field: string;
  op: RuleConditionOp;
  value?: unknown;
}

export interface RuleConditionsJson {
  match?: "all" | "any";
  conditions?: RuleCondition[];
}

export type RuleAction = { type: RuleActionType } & Record<string, unknown>;

export interface AutomationRuleBase {
  name: string;
  description?: string | null;
  event_type: string;
  conditions_json: RuleConditionsJson;
  actions_json: RuleAction[];
  priority: number;
  is_enabled: boolean;
}

export type AutomationRuleCreate = AutomationRuleBase;

export type AutomationRuleUpdate = Partial<AutomationRuleBase>;

export interface AutomationRuleRead extends AutomationRuleBase {
  id: string;
  created_at: string;
  updated_at: string;
}

export interface AutomationRulePage {
  items: AutomationRuleRead[];
  total: number;
  limit: number;
  offset: number;
}

export interface EventFieldMeta {
  name: string;
  kind: string;
}

export interface EventTypeMeta {
  event_type: string;
  fields: EventFieldMeta[];
}

export interface EventTypePage {
  items: EventTypeMeta[];
  total: number;
}

/** Роль-получатель уведомления словами — `GET /rules/recipient-roles` (срез-148). */
export interface RecipientRoleOption {
  code: string;
  label: string;
}

export interface RecipientRolePage {
  items: RecipientRoleOption[];
  total: number;
}

/** Покрытие одной дисциплины библиотекой правил (BIZ-54-57 срез-4). */
export interface RuleLibraryDiscipline {
  discipline: string;
  title: string;
  rules: number;
  /** Почему правил нет. Пусто у дисциплин, где правила есть. */
  reason: string;
  /** Имена правил дисциплины, ни разу не выданных арендатору (срез-66). */
  missing: string[];
  /** Имена правил дисциплины, удалённых специалистом: выдача не вернёт. */
  removed: string[];
}

export interface RuleLibraryPage {
  items: RuleLibraryDiscipline[];
  total: number;
  /** Сколько правил библиотеки уже заведено у арендатора. */
  installed: number;
  /** Сколько правил библиотеки специалист удалил — выдача их не вернёт (срез-63). */
  removed: number;
}

/** Итог выдачи недостающих правил библиотеки (BIZ-54-57 срез-63). */
export interface RuleLibraryInstallOut {
  /** Имена заведённых сейчас правил. */
  created: string[];
  /** Имена правил, удалённых специалистом ранее: не вернули. */
  kept_deleted: string[];
  installed: number;
  total: number;
}

export interface DryRunEvent {
  event_type: string;
  payload: Record<string, unknown>;
}

export interface DryRunIn {
  rule: AutomationRuleBase;
  event: DryRunEvent;
}

export interface ConditionResult {
  field: string;
  op: string;
  value?: unknown;
  actual?: unknown;
  matched: boolean;
}

export interface DryRunOut {
  matched: boolean;
  condition_results: ConditionResult[];
  would_actions: string[];
}

export interface RuleTestResultItem {
  event_key: string;
  occurred_at?: string | null;
  matched: boolean;
}

export interface RuleTestOut {
  events_checked: number;
  matched_count: number;
  results: RuleTestResultItem[];
}

export interface TriggerRead {
  id: string;
  rule_id: string;
  event_type: string;
  event_key: string;
  correlation_id?: string | null;
  status: TriggerStatus;
  actions_result: Record<string, unknown>[];
  created_at: string;
}

export interface TriggerPage {
  items: TriggerRead[];
  total: number;
  limit: number;
  offset: number;
}
