import { z } from "zod";

const optionalText = z
  .string()
  .optional()
  .transform((s) => (s === undefined ? s : s.trim()));

/** Число смен живёт в поле ввода строкой; пусто — ноль (превращает форма). */
const shifts = (label: string) =>
  z.string().trim().regex(/^\d*$/, `${label}: целое число не меньше нуля`);

export const internshipFormSchema = z
  .object({
    person_id: z.string().trim().min(1, "Выберите стажёра"),
    mentor_person_id: optionalText,
    discipline: optionalText,
    subject: optionalText,
    planned_shifts: shifts("Смен по плану"),
    completed_shifts: shifts("Смен пройдено"),
    started_on: optionalText,
    finished_on: optionalText,
    status: z.string().trim().min(1, "Выберите состояние"),
    notes: optionalText,
  })
  // Та же проверка стоит на сервере; здесь — чтобы человек увидел ошибку у
  // поля сразу, а не после запроса. «Сам у себя» — либо опечатка, либо
  // приписка, и в обоих случаях запись врёт о главном: что человека кто-то учил.
  .refine((v) => !v.mentor_person_id || v.mentor_person_id !== v.person_id, {
    message: "Наставник не может быть стажёром: это одна и та же запись",
    path: ["mentor_person_id"],
  });

export type InternshipFormValues = z.infer<typeof internshipFormSchema>;

/** Пустая строка в поле смен — ноль, как и default у бэкенда. */
export const shiftsToNumber = (value: string | undefined): number =>
  value === undefined || value.trim() === "" ? 0 : Number(value);
