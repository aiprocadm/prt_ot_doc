import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

const optionalVolume = z
  .string()
  .trim()
  .regex(/^\d*([.,]\d{1,3})?$/, "Объём: число кубометров, до трёх знаков")
  .optional();

/**
 * Точка водопользования (разд. 55.2, срез-101).
 *
 * ГРАНИЦА: платформа не решает, нужно ли точке разрешение — забор из
 * городского водопровода идёт по договору без срока. Поэтому и разрешение, и
 * его срок необязательны, а пустой срок — не просрочка.
 */
export const ecologyWaterPointFormSchema = z.object({
  facility_id: z.string().trim().min(1, "Выберите объект НВОС"),
  point_number: z.string().trim().min(1, "Внесите номер точки"),
  name: z.string().trim().min(1, "Назовите точку"),
  kind: z.string().trim().min(1, "Выберите вид точки"),
  annual_limit_cubic_meters: optionalVolume,
  permit_valid_until: optionalText,
  water_body: optionalText,
  permit_number: optionalText,
  notes: optionalText,
});

export type EcologyWaterPointFormValues = z.infer<
  typeof ecologyWaterPointFormSchema
>;

/**
 * Запись учёта водопользования (разд. 55.2, срез-101).
 *
 * Единица учёта — месяц: «точка + год + месяц» уникальны на уровне базы, две
 * записи за один месяц означают ошибку ввода. Ноль кубометров принимается:
 * месяц без водопользования — это факт, а не пустая запись.
 */
export const ecologyWaterRecordFormSchema = z.object({
  point_id: z.string().trim().min(1, "Выберите точку водопользования"),
  period_year: z
    .string()
    .trim()
    .regex(/^\d{4}$/, "Год: четыре цифры")
    .refine((v) => Number(v) >= 2000 && Number(v) <= 2100, {
      message: "Год от 2000 до 2100",
    }),
  period_month: z.string().trim().min(1, "Выберите месяц"),
  volume_cubic_meters: z
    .string()
    .trim()
    .min(1, "Внесите объём в кубометрах")
    .regex(/^\d+([.,]\d{1,3})?$/, "Объём: число кубометров, до трёх знаков"),
  basis: z.string().trim().min(1, "Выберите основание учёта"),
  meter_number: optionalText,
  notes: optionalText,
});

export type EcologyWaterRecordFormValues = z.infer<
  typeof ecologyWaterRecordFormSchema
>;
