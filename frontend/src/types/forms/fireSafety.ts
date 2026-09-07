import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/**
 * Средство защиты или система ПБ (разд. 54.1, срез-103).
 *
 * ГРАНИЦА: платформа не решает, какой срок нужен этому средству — перезарядка
 * огнетушителя, поверка крана и испытание лестницы живут по разным правилам, а
 * характеристик средства для вывода в данных нет. Оба срока необязательны, и
 * пустой срок означает «не применимо», а не «просрочено».
 */
export const fireEquipmentFormSchema = z.object({
  kind: z.string().trim().min(1, "Выберите вид средства"),
  label: z.string().trim().min(1, "Внесите наименование или инвентарный номер"),
  site_id: optionalText,
  location: optionalText,
  recharge_due: optionalText,
  inspection_due: optionalText,
});

export type FireEquipmentFormValues = z.infer<typeof fireEquipmentFormSchema>;

/**
 * Документ ПБ (разд. 54.1, срез-103).
 *
 * ГРАНИЦА: платформа НЕ объявляет, какие документы объекту обязательны —
 * декларация нужна не всем объектам, план эвакуации не всем этажам. Форма
 * заводит то, что есть; пустой срок пересмотра означает «бессрочный».
 */
export const fireDocumentFormSchema = z.object({
  kind: z.string().trim().min(1, "Выберите вид документа"),
  title: z.string().trim().min(1, "Назовите документ"),
  site_id: optionalText,
  number: optionalText,
  review_due: optionalText,
  approved_on: optionalText,
  location: optionalText,
  responsible: optionalText,
  notes: optionalText,
});

export type FireDocumentFormValues = z.infer<typeof fireDocumentFormSchema>;

/**
 * Запись о регламентной работе (разд. 54.1, срез-103).
 *
 * Работа — это ДОКАЗАТЕЛЬСТВО исправности: у неё обязательны средство, вид,
 * дата и результат. Следующий срок необязателен: если его не внести, сервер
 * сам сдвинет срок средства по результату — «неисправно» срок НЕ двигает,
 * иначе просрочка исчезла бы с экрана, а неисправность осталась.
 */
export const fireMaintenanceFormSchema = z.object({
  equipment_id: z.string().trim().min(1, "Выберите средство"),
  kind: z.string().trim().min(1, "Выберите вид работы"),
  performed_on: z.string().trim().min(1, "Внесите дату работы"),
  result: z.string().trim().min(1, "Выберите результат"),
  performer: optionalText,
  next_due: optionalText,
  notes: optionalText,
});

export type FireMaintenanceFormValues = z.infer<
  typeof fireMaintenanceFormSchema
>;

/**
 * Тренировка или учение по ПБ (разд. 54.1, срез-104).
 *
 * Тренировка рождается ЗАПЛАНИРОВАННОЙ: вид, название и дата плана
 * обязательны. Протокол — вторая половина записи, и он обязан быть цельным:
 * проведена → есть результат, результат → есть дата проведения. Оба правила
 * стоят и на сервере; здесь они показывают ошибку сразу у поля, а не после
 * запроса. Дата проведения в будущем — это план, а не протокол.
 */
export const fireDrillFormSchema = z
  .object({
    kind: z.string().trim().min(1, "Выберите вид тренировки"),
    title: z.string().trim().min(1, "Назовите тренировку"),
    planned_on: z.string().trim().min(1, "Внесите дату по плану"),
    site_id: optionalText,
    held_on: optionalText,
    outcome: optionalText,
    participants: z
      .string()
      .trim()
      .regex(/^\d*$/, "Участники: целое число")
      .optional(),
    scenario: optionalText,
    findings: optionalText,
  })
  .refine((v) => !v.held_on || Boolean(v.outcome), {
    message: "У проведённой тренировки обязателен результат",
    path: ["outcome"],
  })
  .refine((v) => !v.outcome || Boolean(v.held_on), {
    message: "Результат без даты проведения — выдумка о событии",
    path: ["held_on"],
  });

export type FireDrillFormValues = z.infer<typeof fireDrillFormSchema>;

/** Пустое поле участников — «не внесено» (null), а не ноль человек. */
export const participantsToPayload = (
  value: string | undefined,
): number | null =>
  value && value.trim() !== "" ? Number(value.trim()) : null;
