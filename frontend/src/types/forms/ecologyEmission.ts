import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/** Норматив живёт в поле строкой; пусто — «не задан», а не ноль. */
const optionalNumber = (label: string) =>
  z
    .string()
    .trim()
    .regex(
      /^\d*([.,]\d{1,6})?$/,
      `${label}: число, до шести знаков после точки`,
    )
    .optional();

/**
 * Источник выбросов (разд. 55.2, срез-100).
 *
 * Номер источника уникален в пределах объекта НВОС — это требование
 * инвентаризации: два источника с одним номером означают, что один из них
 * заведён дважды, и любой счёт по объекту стал бы враньём.
 */
export const ecologyEmissionSourceFormSchema = z.object({
  facility_id: z.string().trim().min(1, "Выберите объект НВОС"),
  source_number: z.string().trim().min(1, "Внесите номер источника"),
  name: z.string().trim().min(1, "Назовите источник"),
  kind: z.string().trim().min(1, "Выберите вид источника"),
  location: optionalText,
  inventoried_on: optionalText,
  notes: optionalText,
});

export type EcologyEmissionSourceFormValues = z.infer<
  typeof ecologyEmissionSourceFormSchema
>;

/**
 * Норматив выброса (ПДВ/НДВ, разд. 55.2, срез-100).
 *
 * Пустой срок разрешения — БЕССРОЧНО, а не «просрочено»: для объектов III
 * категории нормативы могут действовать без срока. Хотя бы один предел
 * (г/с или т/год) обязателен: норматив без величины ничего не ограничивает.
 */
export const ecologyEmissionNormFormSchema = z
  .object({
    source_id: z.string().trim().min(1, "Выберите источник выбросов"),
    substance: z.string().trim().min(1, "Назовите вещество"),
    limit_grams_per_second: optionalNumber("Предел, г/с"),
    limit_tons_per_year: optionalNumber("Предел, т/год"),
    permit_number: optionalText,
    valid_until: optionalText,
    notes: optionalText,
  })
  .refine(
    (v) =>
      Boolean(v.limit_grams_per_second?.trim()) ||
      Boolean(v.limit_tons_per_year?.trim()),
    {
      message: "Внесите хотя бы один предел: г/с или т/год",
      path: ["limit_grams_per_second"],
    },
  );

export type EcologyEmissionNormFormValues = z.infer<
  typeof ecologyEmissionNormFormSchema
>;

/** Пустое числовое поле — «не задано» (null), непустое — с точкой. */
export const numberToPayload = (value: string | undefined): string | null =>
  value && value.trim() !== "" ? value.trim().replace(",", ".") : null;
