import { z } from "zod";

export const SAFETY_SYSTEM_CODES = [
  "restraint", "positioning", "fall_arrest", "rescue_evacuation", "access",
] as const;

export const GAS_PARAMETER_CODES = ["oxygen", "flammable", "harmful"] as const;
export const VENTILATION_CODES = ["natural", "forced", "none", "not_required"] as const;
export const FIRE_FIGHTING_MEANS_CODES = [
  "extinguisher_powder", "extinguisher_co2", "water", "sand", "felt", "fire_hose",
] as const;

const gasMeasurementSchema = z.object({
  parameter: z.enum(GAS_PARAMETER_CODES),
  value: z.string(),
  norm: z.string().optional(),
  measured_at: z.string().optional(),
});

export const confinedEnvSchema = z.object({
  gas_analysis: z.array(gasMeasurementSchema).optional(),
  ventilation: z.enum(VENTILATION_CODES).optional(),
});
export type ConfinedEnvValues = z.infer<typeof confinedEnvSchema>;

export const fireSafetySchema = z.object({
  fire_fighting_means: z.array(z.enum(FIRE_FIGHTING_MEANS_CODES)).optional(),
  gas_analysis: z.array(gasMeasurementSchema).optional(),
});
export type FireSafetyValues = z.infer<typeof fireSafetySchema>;

// Надмножество ключей обоих видов — клиентская форма; серверная validate_type_specific — источник истины по виду.
export const typeSpecificSchema = confinedEnvSchema.merge(fireSafetySchema);

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
  type_specific: typeSpecificSchema.nullable().optional(),
});

export type WorkPermitFormValues = z.infer<typeof workPermitSchema>;
