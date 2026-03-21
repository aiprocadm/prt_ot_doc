import { z } from "zod";

export const templateSchema = z.object({
  code: z.string().min(2),
  name: z.string().min(3),
  description: z.string().optional(),
  template_type: z.string().optional(),
  status: z.enum(["draft", "active", "archived"]).default("draft"),
  scope: z.object({
    type: z.enum(["tenant", "organization", "site", "global"]),
    company_id: z.string().optional(),
    site_id: z.string().optional()
  }).default({ type: "tenant" })
});

export type TemplateFormValues = z.infer<typeof templateSchema>;
