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
