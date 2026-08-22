import { z } from "zod";

const trimStr = z.string().transform((s) => s.trim());

const innOrEmpty = trimStr.refine(
  (val) => val === "" || /^\d{10}$/.test(val) || /^\d{12}$/.test(val),
  "ИНН: 10 или 12 цифр, либо оставьте пустым",
);

const kppOrEmpty = trimStr.refine(
  (val) => val === "" || /^\d{9}$/.test(val),
  "КПП — 9 цифр",
);

const ogrnOrEmpty = trimStr.refine(
  (val) => val === "" || /^\d{13}$/.test(val) || /^\d{15}$/.test(val),
  "ОГРН — 13 цифр или ОГРНИП — 15",
);

const optionalEmail = trimStr.pipe(
  z.union([z.literal(""), z.string().email("Некорректный email")]),
);

const optionalWebsite = trimStr
  .refine(
    (val) => val === "" || /^https?:\/\//i.test(val),
    "Укажите адрес с http:// или https://",
  )
  .pipe(z.union([z.literal(""), z.string().url("Некорректный URL")]));

export const companySchema = z.object({
  name: z.string().trim().min(1, "Укажите название"),
  inn: innOrEmpty,
  kpp: kppOrEmpty.optional(),
  ogrn: ogrnOrEmpty.optional(),
  address: z
    .string()
    .optional()
    .transform((s) => (s == null || s === "" ? undefined : s.trim())),
  email: optionalEmail,
  phone: trimStr.optional(),
  /** В UI для справки; в API компании поля website пока нет — не отправляется на бэкенд. */
  website: optionalWebsite,
  status: z.enum(["draft", "active", "archived"]),
  /** BIZ-53 (разд. 53.3): id головной компании группы; "" = без группы. */
  parent_company_id: z.string().optional(),
  tags: z.array(z.string()).optional(),
  person_ids: z.array(z.string()).optional(),
});

export type CompanyFormValues = z.infer<typeof companySchema>;
