import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import type { ApiError } from "@/types/dto/common";
import type { CreateRiskAssessmentDto, HazardDto, RiskAssessmentDto } from "@/types/dto/risk";

type RiskRegistryItem = {
  id: string;
  company_id: string;
  hazard: string;
  probability: number;
  severity: number;
  level: number;
};

type RiskRegistryResponse = {
  items: RiskRegistryItem[];
};

interface RiskState {
  hazards: HazardDto[];
  assessments: RiskAssessmentDto[];
  loading: boolean;
  error: ApiError | null;
  listHazards: () => Promise<void>;
  listAssessments: (companyId?: string) => Promise<void>;
  createAssessment: (payload: CreateRiskAssessmentDto) => Promise<RiskAssessmentDto>;
  exportAssessment: (id: string) => Promise<Blob>;
  reset: () => void;
}

export const useRiskStore = create<RiskState>()(
  immer((set) => ({
    hazards: [],
    assessments: [],
    loading: false,
    error: null,
    listHazards: async () => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      try {
        const { data } = await apiClient.get<RiskRegistryResponse>("/risks");
        const byHazard = new Map<string, HazardDto>();
        for (const item of data.items ?? []) {
          if (!item.hazard || byHazard.has(item.hazard)) continue;
          const nowIso = new Date().toISOString();
          byHazard.set(item.hazard, {
            id: item.hazard,
            created_at: nowIso,
            updated_at: nowIso,
            code: item.hazard,
            title: item.hazard,
            description: "",
            probability: Number(item.probability ?? 1),
            severity: Number(item.severity ?? 1)
          });
        }
        set((state) => {
          state.hazards = Array.from(byHazard.values());
        });
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
      } finally {
        set((state) => {
          state.loading = false;
        });
      }
    },
    listAssessments: async (companyId) => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      try {
        const { data } = await apiClient.get<RiskRegistryResponse>("/risks", {
          params: companyId ? { company_id: companyId } : undefined,
        });
        const mapped: RiskAssessmentDto[] = (data.items ?? []).map((item) => {
          const nowIso = new Date().toISOString();
          return {
          id: item.id,
          created_at: nowIso,
          updated_at: nowIso,
          company_id: item.company_id,
          hazards: [
            {
              hazard_id: item.hazard,
              mitigations: "",
              probability: Number(item.probability ?? 1),
              severity: Number(item.severity ?? 1),
            },
          ],
          total_score: Number(item.level ?? 0),
          status: "approved",
          };
        });
        set((state) => {
          state.assessments = mapped;
        });
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
      } finally {
        set((state) => {
          state.loading = false;
        });
      }
    },
    createAssessment: async (payload) => {
      const { data } = await apiClient.post<RiskAssessmentDto>("/risk/assessments", payload);
      set((state) => {
        state.assessments.unshift(data);
      });
      return data;
    },
    exportAssessment: async (id) => {
      const { data } = await apiClient.get<Blob>(`/risk/assessments/${id}/export`, {
        responseType: "blob"
      });
      return data;
    },
    reset: () => {
      set(() => ({
        hazards: [],
        assessments: [],
        loading: false,
        error: null
      }));
    }
  }))
);
