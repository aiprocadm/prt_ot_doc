import { create } from "zustand";
import { immer } from "zustand/middleware/immer";

import { apiClient } from "@/api/client";
import type { ApiError } from "@/types/dto/common";
import type { DashboardSummaryDto } from "@/types/dto/dashboard";

interface DashboardState {
  summary: DashboardSummaryDto | null;
  loading: boolean;
  error: ApiError | null;
  fetchSummary: () => Promise<void>;
  reset: () => void;
}

export const useDashboardStore = create<DashboardState>()(
  immer((set) => ({
    summary: null,
    loading: false,
    error: null,
    fetchSummary: async () => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      try {
        const { data } = await apiClient.get<DashboardSummaryDto>("/dashboard/summary");
        set((state) => {
          state.summary = data;
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
    reset: () => {
      set(() => ({
        summary: null,
        loading: false,
        error: null
      }));
    }
  }))
);
