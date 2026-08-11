import { z } from "zod";

export const permitFormSchema = z.object({
  person_id: z.string().trim().min(1, "Выберите сотрудника"),
  permit_type: z.string().trim().min(1, "Укажите тип допуска"),
  issued_at: z
    .string()
    .optional()
    .transform((s) => (s === undefined ? s : s.trim())),
  valid_until: z
    .string()
    .optional()
    .transform((s) => (s === undefined ? s : s.trim())),
});

export type PermitFormValues = z.infer<typeof permitFormSchema>;
