import { z } from "zod";

export const SAFETY_SYSTEM_CODES = [
  "restraint", "positioning", "fall_arrest", "rescue_evacuation", "access",
] as const;

export const workPermitSchema = z.object({
  work_type: z.string().min(1, "Укажите вид работ"),
  number: z.string().optional(),
  subdivision_text: z.string().optional(),
  site_id: z.string().optional(),
  zone_text: z.string().min(1, "Укажите зону работ"),
  planned_start: z.string().optional(),
  planned_end: z.string().optional(),
  content_text: z.string().optional(),
  conditions_text: z.string().optional(),
  hazards_text: z.string().optional(),
  safety_systems: z.array(z.enum(SAFETY_SYSTEM_CODES)).optional(),
  measures_before_text: z.string().optional(),
  measures_during_text: z.string().optional(),
  special_conditions_text: z.string().optional(),
  ppe_text: z.string().optional(),
});

export type WorkPermitFormValues = z.infer<typeof workPermitSchema>;
