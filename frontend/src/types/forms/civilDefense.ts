import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/**
 * Нештатное формирование ГО (разд. 56.1, срез-109).
 *
 * ГРАНИЦА: платформа НЕ решает, сколько формирований нужно организации и
 * достаточен ли их штат — это определяют категория по ГО и орган управления
 * ГОЧС. Командир необязателен: формирование заводят до приказа о назначении,
 * а «без командира» отдельно считается в сводке.
 */
export const cdFormationFormSchema = z.object({
  name: z.string().trim().min(1, "Назовите формирование"),
  kind: z.string().trim().min(1, "Выберите вид формирования"),
  purpose: optionalText,
  commander_person_id: optionalText,
  equipment_notes: optionalText,
  notes: optionalText,
});

export type CdFormationFormValues = z.infer<typeof cdFormationFormSchema>;

/**
 * Строка состава формирования (разд. 56.1, срез-109).
 *
 * ФИО не хранится: человек берётся из ядра. Вывод из состава — ДАТА, а не
 * удаление строки: история участия нужна и после того, как человека вывели.
 */
export const cdFormationMemberFormSchema = z
  .object({
    person_id: z.string().trim().min(1, "Выберите работника"),
    role_in_formation: optionalText,
    assigned_on: optionalText,
    released_on: optionalText,
    notes: optionalText,
  })
  .refine(
    (v) => !v.assigned_on || !v.released_on || v.released_on >= v.assigned_on,
    {
      message: "Вывод из состава раньше включения: проверьте даты",
      path: ["released_on"],
    },
  );

export type CdFormationMemberFormValues = z.infer<
  typeof cdFormationMemberFormSchema
>;

/**
 * Учение или тренировка ГО (разд. 56.1, срез-109).
 *
 * Учение рождается ЗАПЛАНИРОВАННЫМ: вид, название и дата плана обязательны.
 * Протокол обязан быть цельным — проведено → есть результат, результат → есть
 * дата проведения (оба правила стоят и на сервере, форма показывает их до
 * запроса). Периодичность учений платформа не назначает: она следует из
 * категории организации по ГО.
 */
export const cdDrillFormSchema = z
  .object({
    kind: z.string().trim().min(1, "Выберите вид учения"),
    title: z.string().trim().min(1, "Назовите учение"),
    planned_on: z.string().trim().min(1, "Внесите дату по плану"),
    formation_id: optionalText,
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
    message: "У проведённого учения обязателен результат",
    path: ["outcome"],
  })
  .refine((v) => !v.outcome || Boolean(v.held_on), {
    message: "Результат без даты проведения — выдумка о событии",
    path: ["held_on"],
  });

export type CdDrillFormValues = z.infer<typeof cdDrillFormSchema>;

/** Пустое число участников — «сведения не внесены», а не «никто не пришёл». */
export const cdParticipantsToPayload = (
  value: string | undefined,
): number | null =>
  value && value.trim() !== "" ? Number(value.trim()) : null;

/**
 * Сведения по ГО об объекте (разд. 56.1, срез-110).
 *
 * ГРАНИЦА: категорирование выполняет ОРГАН — платформа категорию не
 * предлагает и не выводит. «Категория не присвоена» — полноценное значение
 * словаря, а не пустое поле: это ответ, а не отсутствие ответа. На объект
 * заводится одна карточка сведений (уникальность держит база).
 */
export const cdProfileFormSchema = z
  .object({
    site_id: z.string().trim().min(1, "Выберите площадку"),
    category: z.string().trim().min(1, "Выберите категорию по ГО"),
    decision_number: optionalText,
    decision_date: optionalText,
    responsible: optionalText,
    notes: optionalText,
  })
  // Присвоенная категория без реквизитов решения — сведения, которые нечем
  // подтвердить перед органом управления ГОЧС.
  .refine(
    (v) =>
      v.category === "none" ||
      Boolean(v.decision_number?.trim()) ||
      Boolean(v.decision_date?.trim()),
    {
      message: "У присвоенной категории укажите номер или дату решения",
      path: ["decision_number"],
    },
  );

export type CdProfileFormValues = z.infer<typeof cdProfileFormSchema>;

/**
 * Документ планирования ГО (разд. 56.1, срез-110).
 *
 * ГРАНИЦА (та же, что у документов ПБ): платформа НЕ объявляет, какие
 * документы объекту обязательны — состав планирования зависит от категории и
 * решений органа. Пустой срок пересмотра означает «бессрочный», а не
 * «просрочен».
 */
export const cdDocumentFormSchema = z.object({
  kind: z.string().trim().min(1, "Выберите вид документа"),
  title: z.string().trim().min(1, "Назовите документ"),
  number: optionalText,
  site_id: optionalText,
  review_due: optionalText,
  approved_on: optionalText,
  responsible: optionalText,
  notes: optionalText,
});

export type CdDocumentFormValues = z.infer<typeof cdDocumentFormSchema>;
