import { z } from "zod";

export const templateSchema = z.object({
  name: z.string().min(3),
  description: z.string().optional(),
  category: z.string().optional(),
  tags: z.array(z.string()).optional(),
  version_id: z.string().optional()
});

export type TemplateFormValues = z.infer<typeof templateSchema>;
