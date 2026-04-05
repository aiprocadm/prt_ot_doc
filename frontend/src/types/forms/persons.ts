import { z } from "zod";

export const personSchema = z.object({
  company_id: z.string().min(1, "Выберите компанию"),
  first_name: z.string().min(1, "Укажите имя"),
  last_name: z.string().min(1, "Укажите фамилию"),
  middle_name: z.string().optional(),
  position: z.string().optional(),
  email: z.union([z.literal(""), z.string().email("Некорректный email")]).optional(),
  phone: z.string().optional(),
  status: z.enum(["active", "inactive", "dismissed"])
});

export type PersonFormValues = z.infer<typeof personSchema>;
