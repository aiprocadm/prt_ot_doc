import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import type { ApiError } from "@/types/dto/common";
import type {
  CreateRiskAssessmentDto,
  HazardDto,
  RiskAssessmentDto,
} from "@/types/dto/risk";

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

/** Ответ `POST /risk/assess` (backend/app/api/routes/risk/_common.py). */
type RiskAssessResponse = {
  assessment_id: string;
  assessment_key: string;
  assessment_version: number;
  risk_card_ids: string[];
  action_plan_id: string | null;
};

interface RiskState {
  hazards: HazardDto[];
  assessments: RiskAssessmentDto[];
  loading: boolean;
  error: ApiError | null;
  listHazards: () => Promise<void>;
  listAssessments: (companyId?: string) => Promise<void>;
  /** Сохранить расчёт и перечитать список: ответ сервера — не запись витрины. */
  createAssessment: (payload: CreateRiskAssessmentDto) => Promise<void>;
  reset: () => void;
}

const isEndpointUnavailable = (error: unknown): boolean => {
  const status = (error as ApiError | undefined)?.status;
  return status === 404 || status === 405;
};

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
            severity: Number(item.severity ?? 1),
          });
        }
        set((state) => {
          state.hazards = Array.from(byHazard.values());
        });
      } catch (error) {
        if (isEndpointUnavailable(error)) {
          set((state) => {
            state.hazards = [];
            state.error = null;
          });
          return;
        }
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
        if (isEndpointUnavailable(error)) {
          set((state) => {
            state.assessments = [];
            state.error = null;
          });
          return;
        }
        set((state) => {
          state.error = error as ApiError;
        });
      } finally {
        set((state) => {
          state.loading = false;
        });
      }
    },
    /**
     * Срез-152: расчёт уходит на `POST /risk/assess` — единственную ручку
     * оценки, которая есть у сервера.
     *
     * До среза витрина слала его на `/risk/assessments`, которого в контракте
     * нет: кнопка «Сохранить расчёт» всегда кончалась 404, то есть ни один
     * расчёт риска через интерфейс сохранить было нельзя. Тело тоже другое:
     * сервер ждёт `items` с КОДОМ опасности (`AssessIn`, `extra="forbid"`),
     * поэтому список опасностей формы перекладывается сюда, а не шлётся как
     * есть. Ответ сервера — идентификаторы расчёта и карточек риска, а не
     * запись витрины, поэтому список перечитывается с сервера: придумывать
     * строку из ответа значило бы показать то, чего в базе может не быть.
     */
    createAssessment: async (payload) => {
      await apiClient.post<RiskAssessResponse>("/risk/assess", {
        company_id: payload.company_id,
        items: payload.hazards.map((hazard) => ({
          hazard_code: hazard.hazard_id,
          probability: hazard.probability,
          severity: hazard.severity,
        })),
      });
      await useRiskStore.getState().listAssessments(payload.company_id);
    },
    reset: () => {
      set(() => ({
        hazards: [],
        assessments: [],
        loading: false,
        error: null,
      }));
    },
  })),
);
