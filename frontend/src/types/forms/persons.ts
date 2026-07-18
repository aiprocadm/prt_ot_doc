import { z } from "zod";

const optionalEmail = z
  .string()
  .transform((s) => s.trim())
  .pipe(z.union([z.literal(""), z.string().email("Некорректный email")]));

export const personSchema = z.object({
  company_id: z.string().trim().min(1, "Выберите компанию"),
  first_name: z.string().trim().min(1, "Укажите имя"),
  last_name: z.string().trim().min(1, "Укажите фамилию"),
  middle_name: z
    .string()
    .optional()
    .transform((s) => (s === undefined ? s : s.trim())),
  position: z
    .string()
    .optional()
    .transform((s) => (s === undefined ? s : s.trim())),
  email: optionalEmail,
  phone: z
    .string()
    .optional()
    .transform((s) => (s === undefined ? s : s.trim())),
  status: z.enum(["active", "inactive", "dismissed"]),
  electrical_group: z.enum(["", "I", "II", "III", "IV", "V"]).optional(),
  electrical_group_valid_until: z.string().optional(),
  /** Все квалификации персоны (merge-safe: хранится как есть, при сабмите патчится electrical_safety_group). */
  qualifications: z.array(z.record(z.unknown())).optional()
});

export type PersonFormValues = z.infer<typeof personSchema>;
