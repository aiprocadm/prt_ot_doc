import type { BaseEntityDto } from "./common";

export interface HazardDto extends BaseEntityDto {
  code: string;
  title: string;
  description?: string;
  category?: string;
  probability: number;
  severity: number;
}

export interface RiskAssessmentDto extends BaseEntityDto {
  company_id: string;
  hazards: Array<{
    hazard_id: string;
    mitigations?: string;
    probability: number;
    severity: number;
  }>;
  total_score: number;
  status: "draft" | "approved";
  exported_file_id?: string;
}

export interface CreateRiskAssessmentDto {
  company_id: string;
  hazards: Array<{
    hazard_id: string;
    mitigations?: string;
    probability: number;
    severity: number;
  }>;
}
