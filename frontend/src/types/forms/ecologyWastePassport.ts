import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/** Масса живёт в поле строкой: пусто — «лимит не установлен», а не ноль. */
const tons = z
  .string()
  .trim()
  .regex(/^\d*([.,]\d{1,3})?$/, "Лимит: число тонн, до трёх знаков после точки")
  .optional();

/**
 * Паспорт отхода (разд. 55.2, срез-99).
 *
 * Класс опасности — из четырёх значений, и это не описка: отходы V класса
 * паспортизации не подлежат. Годовой лимит берётся из НООЛР или декларации —
 * платформа его не рассчитывает, поэтому поле необязательное, а пустое
 * значит «лимит не установлен» (без него превышения быть не может).
 */
export const ecologyWastePassportFormSchema = z.object({
  name: z.string().trim().min(1, "Назовите вид отхода"),
  fkko_code: z.string().trim().min(1, "Внесите код ФККО"),
  hazard_class: z.string().trim().min(1, "Выберите класс опасности"),
  facility_id: optionalText,
  annual_limit_tons: tons,
  approved_on: optionalText,
  notes: optionalText,
});

export type EcologyWastePassportFormValues = z.infer<
  typeof ecologyWastePassportFormSchema
>;

/** Запятую в тоннах приводим к точке: сервер принимает число, а не текст. */
export const tonsToPayload = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim().replace(",", ".") : null;
