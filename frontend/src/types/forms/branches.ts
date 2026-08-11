import { z } from "zod";

const trimStr = z.string().transform((s) => s.trim());

const optionalEmail = trimStr.pipe(
  z.union([z.literal(""), z.string().email("Некорректный email")]),
);

export const branchSchema = z.object({
  company_id: z.string().trim().min(1, "Выберите компанию"),
  name: z.string().trim().min(1, "Укажите название"),
  code: trimStr.optional(),
  address: trimStr.optional(),
  contact_name: trimStr.optional(),
  contact_phone: trimStr.optional(),
  contact_email: optionalEmail,
  status: z.string().trim().min(1, "Укажите статус").max(32),
});

export type BranchFormValues = z.infer<typeof branchSchema>;
