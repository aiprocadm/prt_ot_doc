import { create } from "zustand";
import { immer } from "zustand/middleware/immer";

import { healthApi, type HealthComprehensiveDto } from "@/api/health";
import type { ApiError } from "@/types/dto/common";

interface HealthState {
  data: HealthComprehensiveDto | null;
  loading: boolean;
  error: ApiError | null;
  fetchComprehensive: (params?: {
    skip_cache?: boolean;
    skip_slow?: boolean;
  }) => Promise<void>;
  reset: () => void;
}

export const useHealthStore = create<HealthState>()(
  immer((set) => ({
    data: null,
    loading: false,
    error: null,
    fetchComprehensive: async (params) => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      try {
        const data = await healthApi.getComprehensive(params);
        set((state) => {
          state.data = data;
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
      set(() => ({ data: null, loading: false, error: null }));
    },
  })),
);
