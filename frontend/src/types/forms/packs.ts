import { z } from "zod";

export const packWizardSchema = z.object({
  company_id: z.string().min(1),
  preset: z.enum([
    "site_entry",
    "incident_response",
    "fire_safety",
    "environmental",
    "custom",
  ]),
  parameters: z.record(z.string(), z.any()).optional(),
});

export type PackWizardValues = z.infer<typeof packWizardSchema>;
