import { z } from "zod";

const innOrEmpty = z
  .string()
  .refine((val) => val === "" || /^\d{10}$/.test(val) || /^\d{12}$/.test(val), "ИНН: 10 или 12 цифр, либо оставьте пустым");

export const companySchema = z.object({
  name: z.string().min(1, "Укажите название"),
  inn: innOrEmpty,
  kpp: z.union([z.literal(""), z.string().regex(/^\d{9}$/, "КПП — 9 цифр")]).optional(),
  ogrn: z.union([z.literal(""), z.string().regex(/^\d{13}$/, "ОГРН — 13 цифр")]).optional(),
  address: z.string().optional(),
  email: z.union([z.literal(""), z.string().email("Некорректный email")]).optional(),
  phone: z.string().optional(),
  website: z.union([z.literal(""), z.string().url("Укажите полный URL, например https://…")]).optional(),
  status: z.enum(["draft", "active", "archived"]),
  tags: z.array(z.string()).optional(),
  person_ids: z.array(z.string()).optional()
});

export type CompanyFormValues = z.infer<typeof companySchema>;
