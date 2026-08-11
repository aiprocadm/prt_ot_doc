import { z } from "zod";

/** Mirrors ``TENANT_SLUG_PATTERN`` in backend/app/schemas/tenant.py — the slug becomes a DB schema name. */
export const TENANT_SLUG_PATTERN = /^[a-z][a-z0-9_-]{1,30}$/;

export const tenantProvisionSchema = z.object({
  slug: z
    .string()
    .trim()
    .toLowerCase()
    .regex(
      TENANT_SLUG_PATTERN,
      "Латиница в нижнем регистре, цифры, - и _; начинается с буквы, от 2 до 31 символа"
    ),
  name: z.string().trim().min(1, "Укажите название").max(200),
  owner_email: z.string().trim().email("Некорректный email"),
  owner_password: z.string().min(8, "Минимум 8 символов").max(128),
  kind: z.enum(["customer", "branch", "contractor"]),
  demo_data: z.boolean()
});

export type TenantProvisionFormValues = z.infer<typeof tenantProvisionSchema>;
