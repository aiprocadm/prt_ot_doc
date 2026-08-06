import { create } from "zustand";
import { immer } from "zustand/middleware/immer";

import {
  operationalDashboardApi,
  type OperationalDashboardDto,
} from "@/api/operationalDashboard";
import type { ApiError } from "@/types/dto/common";

interface OperationalDashboardState {
  data: OperationalDashboardDto | null;
  loading: boolean;
  error: ApiError | null;
  fetchDashboard: () => Promise<void>;
  reset: () => void;
}

export const useOperationalDashboardStore = create<OperationalDashboardState>()(
  immer((set) => ({
    data: null,
    loading: false,
    error: null,
    fetchDashboard: async () => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      try {
        const data = await operationalDashboardApi.getDashboard();
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
