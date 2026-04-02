import { z } from "zod";

export const templateScopeSchema = z.object({
  type: z.enum(["tenant", "organization", "site", "global", "system", "legal_entity"]).default("tenant"),
  tenant_id: z.string().optional(),
  company_id: z.string().optional(),
  site_id: z.string().optional(),
  label: z.string().optional(),
  applicability: z.string().optional()
});

export const templateSchema = z.object({
  code: z.string().min(2),
  name: z.string().min(3),
  description: z.string().optional(),
  category: z.string().optional(),
  status: z.enum(["draft", "active", "archived"]).default("draft"),
  scope: templateScopeSchema.default({ type: "tenant" }),
  tags: z.array(z.string()).optional(),
  version_id: z.string().optional(),
  template_type: z.string().optional()
});

export type TemplateFormValues = z.infer<typeof templateSchema>;
