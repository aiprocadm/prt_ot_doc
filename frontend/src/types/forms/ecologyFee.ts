import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

const year = z
  .string()
  .trim()
  .regex(/^\d{4}$/, "Год: четыре цифры")
  .refine((v) => Number(v) >= 2000 && Number(v) <= 2100, {
    message: "Год от 2000 до 2100",
  });

/**
 * Ставка платы за НВОС (разд. 55.3, срез-102).
 *
 * ГРАНИЦА: ставку устанавливает Правительство и меняет ежегодно — платформа её
 * не знает и не подсказывает. Форма переносит внесённое из постановления,
 * поэтому поле «Ставка, ₽/т» обязательно, а «откуда взята» (реквизиты
 * документа) живёт рядом.
 */
export const ecologyFeeRateFormSchema = z.object({
  year,
  impact_kind: z.string().trim().min(1, "Выберите вид воздействия"),
  subject: z.string().trim().min(1, "Назовите предмет платы"),
  rate_per_ton: z
    .string()
    .trim()
    .min(1, "Внесите ставку из постановления")
    .regex(/^\d+([.,]\d{1,2})?$/, "Ставка: рубли за тонну, до двух знаков"),
  source_document: optionalText,
  notes: optionalText,
});

export type EcologyFeeRateFormValues = z.infer<typeof ecologyFeeRateFormSchema>;

/**
 * Строка расчёта платы (разд. 55.3, срез-102).
 *
 * Квартал — он же авансовый платёж. Коэффициент строго больше нуля: ноль
 * обнулил бы плату, а такого коэффициента не бывает; по умолчанию 1 —
 * «без повышающего коэффициента».
 */
export const ecologyFeeLineFormSchema = z.object({
  year,
  quarter: z.string().trim().min(1, "Выберите квартал"),
  impact_kind: z.string().trim().min(1, "Выберите вид воздействия"),
  subject: z.string().trim().min(1, "Назовите предмет платы"),
  mass_tons: z
    .string()
    .trim()
    .min(1, "Внесите массу в тоннах")
    .regex(/^\d+([.,]\d{1,3})?$/, "Масса: число тонн, до трёх знаков"),
  coefficient: z
    .string()
    .trim()
    .min(1, "Внесите коэффициент (1 — без повышающего)")
    .regex(/^\d+([.,]\d{1,2})?$/, "Коэффициент: число, до двух знаков")
    .refine((v) => Number(v.replace(",", ".")) > 0, {
      message: "Коэффициент больше нуля: нулевой обнулил бы плату",
    })
    .refine((v) => Number(v.replace(",", ".")) <= 200, {
      message: "Коэффициент не больше 200",
    }),
  notes: optionalText,
});

export type EcologyFeeLineFormValues = z.infer<typeof ecologyFeeLineFormSchema>;

/** Запятую в числе приводим к точке: сервер ждёт число, а не текст. */
export const feeNumberToPayload = (value: string): string =>
  value.trim().replace(",", ".");
