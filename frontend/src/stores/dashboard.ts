import { create } from "zustand";
import { immer } from "zustand/middleware/immer";

import { dashboardApi } from "@/api/dashboard";
import { apiClient } from "@/api/client";
import type { ApiError } from "@/types/dto/common";
import type {
  DashboardOperationalSnapshotDto,
  DashboardSummaryDto,
} from "@/types/dto/dashboard";

interface DashboardState {
  summary: DashboardSummaryDto | null;
  operational: DashboardOperationalSnapshotDto | null;
  loading: boolean;
  operationalLoading: boolean;
  error: ApiError | null;
  operationalError: ApiError | null;
  fetchSummary: () => Promise<void>;
  fetchOperational: () => Promise<void>;
  reset: () => void;
}

export const useDashboardStore = create<DashboardState>()(
  immer((set) => ({
    summary: null,
    operational: null,
    loading: false,
    operationalLoading: false,
    error: null,
    operationalError: null,
    fetchSummary: async () => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      try {
        const { data } =
          await apiClient.get<DashboardSummaryDto>("/dashboard/summary");
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
    fetchOperational: async () => {
      set((state) => {
        state.operationalLoading = true;
        state.operationalError = null;
      });
      try {
        const data = await dashboardApi.getOperationalSnapshot();
        set((state) => {
          state.operational = data;
        });
      } catch (error) {
        set((state) => {
          state.operationalError = error as ApiError;
        });
      } finally {
        set((state) => {
          state.operationalLoading = false;
        });
      }
    },
    reset: () => {
      set(() => ({
        summary: null,
        operational: null,
        loading: false,
        operationalLoading: false,
        error: null,
        operationalError: null,
      }));
    },
  })),
);
