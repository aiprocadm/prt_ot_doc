import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/** Масса живёт в поле строкой; ноль сервер не принимает — пустая запись. */
const tons = z
  .string()
  .trim()
  .min(1, "Внесите массу в тоннах")
  .regex(/^\d+([.,]\d{1,3})?$/, "Масса: число тонн, до трёх знаков после точки")
  .refine((v) => Number(v.replace(",", ".")) > 0, {
    message: "Масса больше нуля: движение без массы ничего не учитывает",
  });

/**
 * Запись журнала учёта отходов (разд. 55.2, срез-100).
 *
 * Дата в будущем не принимается: журнал фиксирует свершившееся, а не
 * планируемое (та же проверка стоит на сервере — здесь она лишь показывает
 * ошибку сразу у поля).
 */
export const ecologyWasteMovementFormSchema = z.object({
  passport_id: z.string().trim().min(1, "Выберите паспорт отхода"),
  kind: z.string().trim().min(1, "Выберите вид движения"),
  happened_on: z.string().trim().min(1, "Внесите дату движения"),
  quantity_tons: tons,
  counterparty: optionalText,
  notes: optionalText,
});

export type EcologyWasteMovementFormValues = z.infer<
  typeof ecologyWasteMovementFormSchema
>;

/** Запятую в тоннах приводим к точке: сервер ждёт число, а не текст. */
export const massToPayload = (value: string): string =>
  value.trim().replace(",", ".");
