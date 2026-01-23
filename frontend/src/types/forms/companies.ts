import { z } from "zod";

export const companySchema = z.object({
  name: z.string().min(3),
  inn: z.string().regex(/^\d{10}$/).or(z.string().regex(/^\d{12}$/)),
  kpp: z.string().regex(/^\d{9}$/).optional().or(z.literal("")),
  ogrn: z.string().regex(/^\d{13}$/).optional().or(z.literal("")),
  address: z.string().optional(),
  email: z.string().email().optional(),
  phone: z.string().optional(),
  website: z.string().url().optional(),
  status: z.enum(["draft", "active", "archived"]),
  tags: z.array(z.string()).optional(),
  person_ids: z.array(z.string()).optional()
});

export type CompanyFormValues = z.infer<typeof companySchema>;
