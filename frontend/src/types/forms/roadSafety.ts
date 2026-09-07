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
