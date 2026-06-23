import { z } from "zod";

export const SAFETY_SYSTEM_CODES = [
  "restraint", "positioning", "fall_arrest", "rescue_evacuation", "access",
] as const;

export const GAS_PARAMETER_CODES = ["oxygen", "flammable", "harmful"] as const;
export const VENTILATION_CODES = ["natural", "forced", "none", "not_required"] as const;
export const FIRE_FIGHTING_MEANS_CODES = [
  "extinguisher_powder", "extinguisher_co2", "water", "sand", "felt", "fire_hose",
] as const;

export const RESPIRATORY_PPE_CODES = [
  "hose_mask", "scba", "isolating_mask", "filter_mask", "air_supply",
] as const;

export const ELECTRICAL_MEASURE_CODES = [
  "disconnect", "lockout_signs", "verify_no_voltage", "grounding", "barriers_signs",
] as const;
export const VOLTAGE_CONDITION_CODES = ["de_energized", "near_live", "away_live"] as const;

export const UTILITY_CODES = ["power_cable", "gas_pipe", "water_sewer", "heating", "comms"] as const;
export const SHORING_METHOD_CODES = ["natural_slopes", "shield_bracing", "sheet_piling", "none_shallow"] as const;

export const excavationSafetySchema = z.object({
  utilities: z.array(z.enum(UTILITY_CODES)).optional(),
  shoring: z.enum(SHORING_METHOD_CODES).optional(),
});
export type ExcavationSafetyValues = z.infer<typeof excavationSafetySchema>;

export const electricalSafetySchema = z.object({
  technical_measures: z.array(z.enum(ELECTRICAL_MEASURE_CODES)).optional(),
  voltage_condition: z.enum(VOLTAGE_CONDITION_CODES).optional(),
});
export type ElectricalSafetyValues = z.infer<typeof electricalSafetySchema>;

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

export const gasWorksSchema = z.object({
  respiratory_ppe: z.array(z.enum(RESPIRATORY_PPE_CODES)).optional(),
  gas_analysis: z.array(gasMeasurementSchema).optional(),
});
export type GasWorksValues = z.infer<typeof gasWorksSchema>;

// Надмножество ключей всех видов — клиентская форма; серверная validate_type_specific — источник истины по виду.
export const typeSpecificSchema = confinedEnvSchema
  .merge(fireSafetySchema)
  .merge(gasWorksSchema)
  .merge(electricalSafetySchema)
  .merge(excavationSafetySchema);

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
