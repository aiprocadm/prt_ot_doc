import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import type { ApiError } from "@/types/dto/common";
import type { CreateRiskAssessmentDto, HazardDto, RiskAssessmentDto } from "@/types/dto/risk";

interface RiskState {
  hazards: HazardDto[];
  assessments: RiskAssessmentDto[];
  loading: boolean;
  error: ApiError | null;
  listHazards: () => Promise<void>;
  listAssessments: (companyId?: string) => Promise<void>;
  createAssessment: (payload: CreateRiskAssessmentDto) => Promise<RiskAssessmentDto>;
  exportAssessment: (id: string) => Promise<Blob>;
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
        const { data } = await apiClient.get<HazardDto[]>("/risk/hazards");
        set((state) => {
          state.hazards = data;
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
        const { data } = await apiClient.get<RiskAssessmentDto[]>("/risk/assessments", {
          params: companyId ? { company_id: companyId } : undefined
        });
        set((state) => {
          state.assessments = data;
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
    }
  }))
);
