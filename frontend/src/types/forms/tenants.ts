import { z } from "zod";

import { TENANT_KINDS } from "@/types/dto/tenants";

/** Mirrors ``TENANT_SLUG_PATTERN`` in backend/app/schemas/tenant.py — the slug becomes a DB schema name. */
export const TENANT_SLUG_PATTERN = /^[a-z][a-z0-9_-]{1,30}$/;

export const tenantProvisionSchema = z.object({
  slug: z
    .string()
    .trim()
    .toLowerCase()
    .regex(
      TENANT_SLUG_PATTERN,
      "Латиница в нижнем регистре, цифры, - и _; начинается с буквы, от 2 до 31 символа",
    ),
  name: z.string().trim().min(1, "Укажите название").max(200),
  owner_email: z.string().trim().email("Некорректный email"),
  owner_password: z.string().min(8, "Минимум 8 символов").max(128),
  kind: z.enum(TENANT_KINDS),
  demo_data: z.boolean(),
  /** Код отрасли. Список закрыт на сервере, поэтому здесь просто строка:
   *  повторить перечисление значило бы завести вторую правду о том, какие
   *  отрасли существуют (BIZ-52 срез-12). */
  industry: z.string(),
});

export type TenantProvisionFormValues = z.infer<typeof tenantProvisionSchema>;
