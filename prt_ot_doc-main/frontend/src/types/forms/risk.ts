import { z } from "zod";

export const riskAssessmentSchema = z.object({
  company_id: z.string().min(1),
  hazards: z
    .array(
      z.object({
        hazard_id: z.string().min(1),
        probability: z.number().min(1).max(5),
        severity: z.number().min(1).max(5),
        mitigations: z.string().optional()
      })
    )
    .min(1)
});

export type RiskAssessmentFormValues = z.infer<typeof riskAssessmentSchema>;
