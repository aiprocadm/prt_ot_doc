import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/**
 * Транспортное средство (разд. 56.2, срез-107).
 *
 * ГРАНИЦА: платформа НЕ решает, нужна ли этому ТС лицензия и обязателен ли
 * тахограф — это следует из вида перевозок, массы и категории. Все сроки
 * необязательны, но пустой срок здесь означает «СВЕДЕНИЯ НЕ ВНЕСЕНЫ», а не
 * «бессрочно»: у диагностической карты и полиса бессрочности не бывает.
 */
export const vehicleFormSchema = z
  .object({
    plate_number: z.string().trim().min(1, "Внесите госномер"),
    brand_model: z.string().trim().min(1, "Внесите марку и модель"),
    kind: z.string().trim().min(1, "Выберите вид ТС"),
    status: z.string().trim().min(1, "Выберите состояние"),
    inspection_due: optionalText,
    insurance_due: optionalText,
    site_id: optionalText,
    vin: optionalText,
    year_made: z
      .string()
      .trim()
      .regex(/^\d*$/, "Год выпуска: четыре цифры")
      .optional(),
    license_number: optionalText,
    license_due: optionalText,
    tachograph_installed: z.boolean().optional(),
    tachograph_due: optionalText,
    notes: optionalText,
  })
  .refine(
    (v) =>
      !v.year_made ||
      (Number(v.year_made) >= 1900 && Number(v.year_made) <= 2100),
    { message: "Год выпуска от 1900 до 2100", path: ["year_made"] },
  )
  // Срок поверки тахографа без самого тахографа — сведения о приборе, которого
  // нет: «не установлен» и «нет сведений о поверке» это разные факты.
  .refine((v) => !v.tachograph_due || v.tachograph_installed, {
    message: "Срок поверки указан, а тахограф не отмечен как установленный",
    path: ["tachograph_due"],
  });

export type VehicleFormValues = z.infer<typeof vehicleFormSchema>;

/** Пустой год — «не внесён» (null), а не нулевой год. */
export const yearToPayload = (value: string | undefined): number | null =>
  value && value.trim() !== "" ? Number(value.trim()) : null;

/**
 * Карточка водителя (разд. 56.2, срез-107).
 *
 * ФИО в карточке нет: человек берётся из ядра. Стаж задаётся ДАТОЙ начала —
 * записанное числом «3 года» через два года молча стало бы ложью. Хотя бы
 * одна категория обязательна: водитель без единой категории — не водитель.
 *
 * ГРАНИЦА: полей «допущен ли к этой машине» и «хватает ли стажа» нет —
 * нужная категория и требуемый стаж следуют из массы ТС, числа мест и вида
 * перевозок по закону.
 */
export const driverFormSchema = z.object({
  person_id: z.string().trim().min(1, "Выберите работника"),
  license_number: z.string().trim().min(1, "Внесите номер удостоверения"),
  categories: z
    .array(z.string())
    .min(1, "Отметьте хотя бы одну категорию: без неё это не водитель"),
  license_due: optionalText,
  status: z.string().trim().min(1, "Выберите состояние допуска"),
  license_issued_at: optionalText,
  experience_since: optionalText,
  notes: optionalText,
});

export type DriverFormValues = z.infer<typeof driverFormSchema>;

/**
 * Путевой лист (разд. 56.2, срез-108).
 *
 * Машина и водитель — ссылки на реестры, номера и фамилии в листе не хранятся:
 * переименование машины иначе оставило бы старое имя в тысяче листов.
 *
 * ГРАНИЦЫ: отметки контроля по умолчанию «сведения не внесены» — свежий лист
 * выписывается ДО осмотра, и это законное состояние, а не нарушение. Полей
 * «законен ли выпуск» и «уложился ли водитель в режим труда и отдыха» нет:
 * обязательность послерейсового осмотра и норма времени следуют из вида
 * перевозок и суммирования за неделю.
 */
export const waybillFormSchema = z
  .object({
    number: z.string().trim().min(1, "Внесите номер листа"),
    vehicle_id: z.string().trim().min(1, "Выберите машину"),
    driver_id: z.string().trim().min(1, "Выберите водителя"),
    issued_on: z.string().trim().min(1, "Внесите дату выдачи"),
    status: z.string().trim().min(1, "Выберите состояние листа"),
    pre_trip_medical: z.string().trim().min(1),
    pre_trip_technical: z.string().trim().min(1),
    post_trip_medical: z.string().trim().min(1),
    departure_at: optionalText,
    return_at: optionalText,
    notes: optionalText,
  })
  // Вернуться раньше, чем выехал, нельзя — это опечатка, а не короткий рейс
  // (та же проверка на сервере).
  .refine(
    (v) => !v.departure_at || !v.return_at || v.return_at >= v.departure_at,
    {
      message: "Возвращение раньше выезда: проверьте даты рейса",
      path: ["return_at"],
    },
  );

export type WaybillFormValues = z.infer<typeof waybillFormSchema>;

/**
 * ДТП (разд. 56.2, срез-108).
 *
 * ГРАНИЦЫ: вину устанавливают ГИБДД и суд — по умолчанию «не установлена», и
 * платформа её не выводит. Тяжесть последствий считается сервером из числа
 * пострадавших и погибших, поля «тяжесть» в форме нет. Водитель обязателен —
 * в отличие от нарушения: за рулём при ДТП кто-то был. Впрочем, в стоящую
 * машину въезжают и без водителя, поэтому сервер разрешает пустое поле, а
 * форма — тоже (выбор «за рулём никого не было»).
 */
export const accidentFormSchema = z.object({
  occurred_at: z.string().trim().min(1, "Внесите дату и время ДТП"),
  place: z.string().trim().min(1, "Внесите место"),
  vehicle_id: z.string().trim().min(1, "Выберите машину"),
  kind: z.string().trim().min(1, "Выберите вид ДТП"),
  driver_id: optionalText,
  fault: z.string().trim().min(1, "Выберите вину"),
  injured_count: z
    .string()
    .trim()
    .regex(/^\d*$/, "Пострадавшие: целое число")
    .optional(),
  fatalities_count: z
    .string()
    .trim()
    .regex(/^\d*$/, "Погибшие: целое число")
    .optional(),
  gibdd_reference: optionalText,
  description: optionalText,
});

export type AccidentFormValues = z.infer<typeof accidentFormSchema>;

/**
 * Нарушение ПДД (разд. 56.2, срез-108).
 *
 * ГРАНИЦЫ: водитель НЕОБЯЗАТЕЛЕН — камера фиксирует госномер, а не человека,
 * и кто был за рулём, организация выясняет сама, иногда никогда. Пустая сумма
 * штрафа означает «штраф НЕ НАЛОЖЕН», а не «сумма неизвестна». Статья КоАП —
 * свободная строка: закрытый словарь отстал бы от поправок.
 */
export const violationFormSchema = z
  .object({
    vehicle_id: z.string().trim().min(1, "Выберите машину"),
    occurred_at: z.string().trim().min(1, "Внесите дату и время"),
    source: z.string().trim().min(1, "Выберите способ выявления"),
    article: optionalText,
    fine_amount: z
      .string()
      .trim()
      .regex(/^\d*([.,]\d{1,2})?$/, "Штраф: сумма в рублях, до двух знаков")
      .optional(),
    driver_id: optionalText,
    resolution_number: optionalText,
    place: optionalText,
    fine_paid_on: optionalText,
    description: optionalText,
  })
  // Отметка об оплате без суммы — оплата штрафа, которого нет.
  .refine((v) => !v.fine_paid_on || Boolean(v.fine_amount?.trim()), {
    message: "Дата оплаты указана, а сумма штрафа не внесена",
    path: ["fine_paid_on"],
  });

export type ViolationFormValues = z.infer<typeof violationFormSchema>;

/** Пустое число — «не внесено» (сервер подставит ноль сам, где нужно). */
export const countToPayload = (value: string | undefined): number =>
  value && value.trim() !== "" ? Number(value.trim()) : 0;

/** Пустая сумма штрафа — «штраф не наложен» (null), а не ноль рублей. */
export const fineToPayload = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim().replace(",", ".") : null;

/** `datetime-local` даёт «2026-09-01T08:30» — сервер ждёт ISO с секундами. */
export const localDateTimeToPayload = (value: string): string =>
  value.length === 16 ? `${value}:00` : value;

/** Обратно для формы: ISO с зоной → значение поля `datetime-local`. */
export const isoToLocalDateTime = (value?: string | null): string =>
  value ? value.slice(0, 16) : "";
