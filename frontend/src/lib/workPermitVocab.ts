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

export const LEGAL_REFERENCE_LABELS: Record<string, string> = {
  height: "Приказ Минтруда № 782н",
  confined_space: "Приказ Минтруда № 902н",
  electrical: "Приказ Минтруда № 903н",
  hot_work: "Постановление Правительства РФ № 1479 (ППР)",
  gas_hazardous: "Приказ Ростехнадзора № 528 (ФНП)",
  excavation: "Правила земляных работ",
};

export const GAS_PARAMETER_LABELS: Record<string, string> = {
  oxygen: "Кислород (O₂), %",
  flammable: "Горючие газы и пары, % НКПР",
  harmful: "Вредные вещества, мг/м³",
};

export const VENTILATION_LABELS: Record<string, string> = {
  natural: "Естественная",
  forced: "Принудительная",
  none: "Не применяется",
  not_required: "Не требуется",
};

export const FIRE_FIGHTING_MEANS_LABELS: Record<string, string> = {
  extinguisher_powder: "Огнетушитель порошковый",
  extinguisher_co2: "Огнетушитель углекислотный",
  water: "Вода (ёмкость/ведро)",
  sand: "Ящик с песком",
  felt: "Кошма / асбестовое полотно",
  fire_hose: "Пожарный кран/рукав",
};

export const RESPIRATORY_PPE_LABELS: Record<string, string> = {
  hose_mask: "Шланговый противогаз (ПШ-1/ПШ-2)",
  scba: "Автономный дыхательный аппарат (ИДА)",
  isolating_mask: "Изолирующий противогаз",
  filter_mask: "Фильтрующий противогаз/респиратор",
  air_supply: "Аппарат с принудительной подачей воздуха",
};

export const ELECTRICAL_MEASURES_LABELS: Record<string, string> = {
  disconnect: "Отключения + меры против ошибочного включения",
  lockout_signs: "Запрещающие плакаты на приводах/ключах",
  verify_no_voltage: "Проверено отсутствие напряжения",
  grounding: "Установлено заземление (ЗН / переносные)",
  barriers_signs: "Плакаты, ограждение мест и токоведущих частей",
};

export const VOLTAGE_CONDITION_LABELS: Record<string, string> = {
  de_energized: "Со снятием напряжения",
  near_live: "Без снятия напряжения вблизи токоведущих частей",
  away_live: "Без снятия напряжения вдали от токоведущих частей",
};

export const labelOf = (map: Record<string, string>, code: string): string =>
  map[code] ?? code;
