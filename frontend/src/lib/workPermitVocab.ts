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
};

export const SAFETY_SYSTEM_LABELS: Record<string, string> = {
  restraint: "Удерживающие системы",
  positioning: "Системы позиционирования",
  fall_arrest: "Страховочные системы",
  rescue_evacuation: "Системы для эвакуации и спасения",
  access: "Системы для подъёма и спуска",
};

export const labelOf = (map: Record<string, string>, code: string): string =>
  map[code] ?? code;
