import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/** Дата из `<input type="date">` — строка ГГГГ-ММ-ДД либо пусто. */
const optionalDate = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/**
 * Срок экологической отчётности или платежа (разд. 55.3, срез-98).
 *
 * Дату сдачи вносит эколог по нормативному акту: платформа её не назначает и
 * не вычисляет (решение среза-23), поэтому срок обязателен, а подсказок «когда
 * сдавать 2-ТП» в форме нет — подставленная дата отстала бы от акта.
 */
export const ecologyReportingFormSchema = z.object({
  kind: z.string().trim().min(1, "Выберите вид: отчётность или платёж"),
  title: z.string().trim().min(1, "Назовите, что сдать или оплатить"),
  period: optionalText,
  due_on: z.string().trim().min(1, "Внесите срок по нормативному акту"),
  done_on: optionalDate,
  responsible: optionalText,
  notes: optionalText,
});

export type EcologyReportingFormValues = z.infer<
  typeof ecologyReportingFormSchema
>;
