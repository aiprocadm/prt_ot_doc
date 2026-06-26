import { apiClient } from "@/api/client";

// ── Types ──────────────────────────────────────────────────────────────────

export interface SoutCampaign {
  id: string;
  name: string;
  expert_org_name?: string | null;
  report_number?: string | null;
  report_date?: string | null;
  status: string;
  planned_date?: string | null;
  completed_date?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SoutCampaignPage {
  items: SoutCampaign[];
  total: number;
  limit: number;
  offset: number;
}

export interface SoutWorkplace {
  id: string;
  campaign_id: string;
  workplace_code: string;
  position_name: string;
  person_id?: string | null;
  assessed_class?: string | null;
  assessment_date?: string | null;
  next_assessment_date?: string | null;
  is_reassessment_due: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface SoutWorkplacePage {
  items: SoutWorkplace[];
  total: number;
  limit: number;
  offset: number;
}

export interface SoutFactor {
  id: string;
  workplace_id: string;
  code?: string | null;
  name: string;
  measured_class?: string | null;
  note?: string | null;
}

export interface SoutGuarantee {
  id: string;
  workplace_id: string;
  kind: string;
  detail?: string | null;
}

export interface SoutWorkplaceReport {
  workplace: SoutWorkplace;
  factors: SoutFactor[];
  guarantees: SoutGuarantee[];
}

export interface SoutCampaignReport {
  campaign: SoutCampaign;
  workplaces: SoutWorkplaceReport[];
}

export interface SoutClassHistoryEntry {
  id: string;
  workplace_id: string;
  old_class?: string | null;
  new_class?: string | null;
  changed_at: string;
  note?: string | null;
  is_worsening: boolean;
}

export interface PpeNormSuggestion {
  position_id: string;
  hazard_id: string;
  hazard_title: string;
  factor_name: string;
  factor_code: string | null;
  measured_class: string | null;
  reason: string;
}

export interface MedicalExamSuggestion {
  position_id: string;
  exam_kind: string;
  periodicity_months: number;
  factor_codes: string[];
  reason: string;
}

export interface NormSuggestions {
  ppe: PpeNormSuggestion[];
  medical: MedicalExamSuggestion[];
}

// ── API ────────────────────────────────────────────────────────────────────

const base = "/sout";

export const soutApi = {
  async list(params: { limit?: number; offset?: number } = {}): Promise<SoutCampaignPage> {
    const r = await apiClient.get<SoutCampaignPage>(base, {
      params: { limit: 100, offset: 0, ...params },
    });
    return r.data;
  },

  async get(id: string): Promise<SoutCampaign> {
    return (await apiClient.get<SoutCampaign>(`${base}/${id}`)).data;
  },

  async listWorkplaces(
    campaignId: string,
    params: { limit?: number; offset?: number } = {},
  ): Promise<SoutWorkplacePage> {
    const r = await apiClient.get<SoutWorkplacePage>(`${base}/${campaignId}/workplaces`, {
      params: { limit: 100, offset: 0, ...params },
    });
    return r.data;
  },

  async getReport(campaignId: string): Promise<SoutCampaignReport> {
    return (await apiClient.get<SoutCampaignReport>(`${base}/${campaignId}/report`)).data;
  },

  async listClassHistory(workplaceId: string): Promise<SoutClassHistoryEntry[]> {
    return (await apiClient.get<SoutClassHistoryEntry[]>(`${base}/workplaces/${workplaceId}/class-history`)).data;
  },

  async getNormSuggestions(workplaceId: string): Promise<NormSuggestions> {
    return (await apiClient.get<NormSuggestions>(`${base}/workplaces/${workplaceId}/norm-suggestions`)).data;
  },

  async linkWorkplacePosition(workplaceId: string, positionId: string): Promise<void> {
    await apiClient.patch(`${base}/workplaces/${workplaceId}`, { position_id: positionId });
  },

  async linkFactorHazard(factorId: string, hazardId: string): Promise<void> {
    await apiClient.patch(`${base}/factors/${factorId}`, { hazard_id: hazardId });
  },
};
