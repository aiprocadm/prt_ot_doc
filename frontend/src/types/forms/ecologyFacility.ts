import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/**
 * Объект НВОС (разд. 55.1, срез-99).
 *
 * Название, код в государственном реестре и категория обязательны: без кода
 * объект не считается поставленным на учёт, а от категории зависят режим
 * надзора и состав отчётности. Категорию платформа НЕ вычисляет — её
 * присваивают при постановке на учёт, форма только даёт выбрать внесённую.
 */
export const ecologyFacilityFormSchema = z
  .object({
    name: z.string().trim().min(1, "Назовите объект"),
    register_number: z
      .string()
      .trim()
      .min(1, "Внесите код объекта из свидетельства об учёте"),
    category: z.string().trim().min(1, "Выберите категорию из свидетельства"),
    site_id: optionalText,
    status: z.string().trim().min(1, "Выберите состояние"),
    registered_on: optionalText,
    actualized_on: optionalText,
    excluded_on: optionalText,
    responsible: optionalText,
    notes: optionalText,
  })
  // Снятие с учёта без даты — запись, по которой нельзя ответить надзору
  // «когда»: состояние говорит «снят», а документа за ним не видно.
  .refine((v) => v.status !== "excluded" || Boolean(v.excluded_on), {
    message: "У снятого с учёта нужна дата снятия",
    path: ["excluded_on"],
  });

export type EcologyFacilityFormValues = z.infer<
  typeof ecologyFacilityFormSchema
>;
