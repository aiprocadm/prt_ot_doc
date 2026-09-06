import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/**
 * Строка плана-графика ПЭК (разд. 55.2, срез-101).
 *
 * ГРАНИЦА: периодичность берётся из утверждённой программы ПЭК — платформа её
 * не назначает. Поэтому поле обязательное и без «рекомендованного» значения;
 * допустимо 1–60 месяцев, как и на сервере (ноль означал бы «никогда»).
 */
export const ecologyMonitoringPlanFormSchema = z.object({
  source_id: z.string().trim().min(1, "Выберите источник выбросов"),
  substance: z.string().trim().min(1, "Назовите вещество"),
  periodicity_months: z
    .string()
    .trim()
    .min(1, "Внесите периодичность из программы ПЭК")
    .regex(/^\d+$/, "Периодичность: целое число месяцев")
    .refine((v) => Number(v) >= 1 && Number(v) <= 60, {
      message: "Периодичность от 1 до 60 месяцев",
    }),
  next_due_on: z.string().trim().min(1, "Внесите дату ближайшего замера"),
  method: optionalText,
  laboratory: optionalText,
  notes: optionalText,
});

export type EcologyMonitoringPlanFormValues = z.infer<
  typeof ecologyMonitoringPlanFormSchema
>;

/**
 * Замер ПЭК (разд. 55.2, срез-101).
 *
 * Строка плана необязательна: замер по предписанию делают вне графика. Если
 * строка указана, сервер сам двигает плановую дату вперёд — форма этого не
 * повторяет.
 */
export const ecologyMeasurementFormSchema = z.object({
  source_id: z.string().trim().min(1, "Выберите источник выбросов"),
  substance: z.string().trim().min(1, "Назовите вещество"),
  measured_on: z.string().trim().min(1, "Внесите дату замера"),
  value_grams_per_second: z
    .string()
    .trim()
    .min(1, "Внесите результат замера в г/с")
    .regex(/^\d+([.,]\d{1,6})?$/, "Результат: число г/с, до шести знаков"),
  plan_id: optionalText,
  protocol_number: optionalText,
  laboratory: optionalText,
  notes: optionalText,
});

export type EcologyMeasurementFormValues = z.infer<
  typeof ecologyMeasurementFormSchema
>;

/** Запятую в числе приводим к точке: сервер ждёт число, а не текст. */
export const decimalToPayload = (value: string): string =>
  value.trim().replace(",", ".");
