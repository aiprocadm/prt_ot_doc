import type {
  RuleActionType,
  RuleConditionOp,
  TriggerStatus,
} from "@/types/dto/rules";

export const OP_LABELS: Record<RuleConditionOp, string> = {
  eq: "равно",
  ne: "не равно",
  in: "одно из",
  not_in: "не из списка",
  gt: "больше",
  gte: "не меньше",
  lt: "меньше",
  lte: "не больше",
  contains: "содержит",
  exists: "заполнено",
};

export const ACTION_LABELS: Record<RuleActionType, string> = {
  create_task: "Создать задачу",
  notify: "Уведомление",
  webhook: "Webhook",
};

/**
 * Кому уходит уведомление. Тот же список — в бэкенде
 * (`app/modules/rules_engine/actions.py`, RECIPIENT_MODE_TITLES); их сверяет
 * сторож `tests/api/test_rules_engine_actions.py`, чтобы описание правила в
 * пробном прогоне и подпись в форме не разъехались.
 *
 * `person` — сам работник из события (по его почте ищется вход в систему);
 * доступен только у событий, где есть поле `person_id`.
 */
export const RECIPIENT_MODE_LABELS: Record<string, string> = {
  actor: "Автор события",
  person: "Работник из события",
  user_id: "Указать user ID",
  role: "По ролям",
};

export const STATUS_LABELS: Record<TriggerStatus, string> = {
  success: "Успех",
  partial: "Частично",
  error: "Ошибка",
};

export const OUTCOME_LABELS: Record<string, string> = {
  created: "создано",
  deduped: "дубль",
  suppressed: "подавлено",
  error: "ошибка",
};

export const EVENT_LABELS: Record<string, string> = {
  IncidentCreated: "Создан инцидент",
  InspectionCreated: "Создана проверка",
  TrainingCompleted: "Обучение завершено",
  TrainingAssigned: "Обучение назначено",
  PPEIssued: "Выдано СИЗ",
  PPEReturned: "Возврат СИЗ",
  PPEWrittenOff: "Списание СИЗ",
  PPEReplacementDue: "Требуется замена СИЗ",
  MedicalExamRecorded: "Медосмотр внесён",
  PersonSuspended: "Отстранение от работы",
  PersonReinstated: "Допуск восстановлен",
  PrescriptionOverdue: "Просрочено предписание",
  DisciplineDeadlineOverdue: "Срок дисциплины просрочен",
  DocumentCreated: "Создан документ",
  DocumentGenerated: "Сгенерирован документ",
  DocumentSigned: "Документ подписан",
  DocumentExported: "Документы выгружены",
  TaskOverdue: "Задача просрочена",
  TaskDueSoon: "Задача скоро истекает",
  RiskAssessed: "Оценён риск",
  "contractor.document_expiring": "Истекает документ подрядчика",
  "contractor.document_expired": "Истёк документ подрядчика",
  "contractor.readiness_blocked": "Подрядчик не допущен",
  "contractor.readiness_warning": "Подрядчик: предупреждение",
  PEPSigned: "ПЭП: подписано",
  PEPDeclined: "ПЭП: отклонено",
};

export const eventLabel = (code: string): string => EVENT_LABELS[code] ?? code;

const KIND_LABELS: Record<string, string> = {
  string: "строка",
  number: "число",
  boolean: "да/нет",
  datetime: "дата-время",
  date: "дата",
  array: "список",
  object: "объект",
};

export const kindLabel = (kind: string): string => KIND_LABELS[kind] ?? kind;
