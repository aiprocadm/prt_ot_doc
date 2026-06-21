export const WORK_TYPE_LABELS: Record<string, string> = {
  hot_work: "Огневые работы",
  gas_hazardous: "Газоопасные работы",
  height: "Работа на высоте",
  confined_space: "Замкнутые пространства",
  excavation: "Земляные работы",
  electrical: "Электроустановки",
};

export const MEMBER_ROLE_LABELS: Record<string, string> = {
  issuer: "Выдающий наряд",
  supervisor: "Ответственный руководитель",
  admitter: "Допускающий",
  foreman: "Производитель работ",
  observer: "Наблюдающий",
  member: "Член бригады",
};

export const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  issued: "Выдан",
  suspended: "Приостановлен",
  closed: "Закрыт",
  cancelled: "Отменён",
};

export const EVENT_TYPE_LABELS: Record<string, string> = {
  issued: "Выдан",
  suspended: "Приостановлен",
  resumed: "Возобновлён",
  closed: "Закрыт",
  cancelled: "Отменён",
  extended: "Продлён",
  admitted: "Ежедневный допуск",
  member_added: "Добавлен участник",
  member_removed: "Удалён участник",
  completion_recorded: "Оформлен акт окончания",
};

export const SAFETY_SYSTEM_LABELS: Record<string, string> = {
  restraint: "Удерживающие системы",
  positioning: "Системы позиционирования",
  fall_arrest: "Страховочные системы",
  rescue_evacuation: "Системы для эвакуации и спасения",
  access: "Системы для подъёма и спуска",
};

export const SIGN_STATUS_LABELS: Record<string, string> = {
  created: "Создан",
  awaiting_code: "Ожидает код",
  signed: "Подписан",
  declined: "Отклонён",
  expired: "Код истёк",
};

export const CLOSING_KIND_LABELS: Record<string, string> = {
  handover: "Сдал (производитель работ)",
  acceptance: "Принял (ответственный/допускающий)",
};

export const CLOSING_MISSING_LABELS: Record<string, string> = {
  completion_act: "не оформлен акт окончания работ",
  handover_signature: "нет подписи «сдал»",
  acceptance_signature: "нет подписи «принял»",
};

export const labelOf = (map: Record<string, string>, code: string): string =>
  map[code] ?? code;
