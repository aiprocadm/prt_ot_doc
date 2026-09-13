import { z } from "zod";

/**
 * Срез-152: поле «Мероприятия» снято из расчёта. Сервер (`AssessIn`,
 * `extra="forbid"`) принимает меры КОДАМИ из справочника `RiskControl`
 * (`controls: list[str]`), свободный текст он бы не сохранил — поле обещало
 * то, чего не происходит. Возврат — вместе с выбором мер из справочника
 * (ручки чтения справочника мер в контракте сейчас тоже нет).
 */

export const riskAssessmentSchema = z.object({
  company_id: z.string().min(1),
  hazards: z
    .array(
      z.object({
        hazard_id: z.string().min(1),
        probability: z.number().min(1).max(5),
        severity: z.number().min(1).max(5),
      }),
    )
    .min(1),
});

export type RiskAssessmentFormValues = z.infer<typeof riskAssessmentSchema>;
