import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { normalizeBranchRead } from "@/api/branchesApi";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState, PaginationParams } from "@/stores/types";
import type { ApiError } from "@/types/dto/common";
import type {
  BranchDto,
  BranchFiltersDto,
  CreateBranchDto,
  UpdateBranchDto
} from "@/types/dto/branches";

/** Ответ GET /branches — плоский { items, total } (BranchPage). */
interface BranchPageResponse {
  items?: unknown;
  total?: number;
}

interface BranchesState extends PaginatedState<BranchDto, BranchFiltersDto> {
  list: (params?: Partial<BranchFiltersDto> & PaginationParams) => Promise<void>;
  create: (payload: CreateBranchDto) => Promise<BranchDto>;
  update: (id: string, payload: UpdateBranchDto) => Promise<BranchDto>;
  remove: (id: string) => Promise<void>;
  setFilters: (filters: Partial<BranchFiltersDto>) => void;
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
  reset: () => void;
}

const createInitialState = () => ({
  items: [] as BranchDto[],
  item: null as BranchDto | null,
  filters: {} as BranchFiltersDto,
  pagination: defaultPagination(),
  loading: false,
  error: null as ApiError | null
});

export const useBranchesStore = create<BranchesState>()(
  immer((set, get) => ({
    ...createInitialState(),
    setFilters: (filters) => {
      set((state) => {
        state.filters = { ...state.filters, ...filters };
        state.pagination.page = 1;
      });
    },
    setPage: (page) => {
      set((state) => {
        state.pagination.page = page;
      });
    },
    setPageSize: (pageSize) => {
      set((state) => {
        state.pagination.page_size = pageSize;
        state.pagination.page = 1;
      });
    },
    reset: () => {
      set(() => createInitialState());
    },
    list: async (params) => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      const { page, page_size: pageSize } = get().pagination;
      const limit = pageSize;
      const offset = (page - 1) * pageSize;
      const companyId = params?.company_id ?? get().filters.company_id;
      const query: Record<string, unknown> = { limit, offset };
      if (companyId) query.company_id = companyId;
      try {
        const { data } = await apiClient.get<BranchPageResponse>("/branches", { params: query });
        const rawItems = Array.isArray(data?.items) ? data.items : [];
        const total = typeof data?.total === "number" ? data.total : rawItems.length;
        set((state) => {
          state.items = rawItems.map((row) => normalizeBranchRead(row));
          state.pagination.total = total;
        });
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
        throw error;
      } finally {
        set((state) => {
          state.loading = false;
        });
      }
    },
    create: async (payload) => {
      const { data } = await apiClient.post<unknown>("/branches", payload);
      const row = normalizeBranchRead(data);
      set((state) => {
        state.items.unshift(row);
        state.pagination.total += 1;
      });
      return row;
    },
    update: async (id, payload) => {
      const { data } = await apiClient.patch<unknown>(`/branches/${id}`, payload);
      const row = normalizeBranchRead(data);
      set((state) => {
        state.items = state.items.map((branch) => (branch.id === id ? row : branch));
        if (state.item?.id === id) {
          state.item = row;
        }
      });
      return row;
    },
    remove: async (id) => {
      await apiClient.delete(`/branches/${id}`);
      set((state) => {
        state.items = state.items.filter((branch) => branch.id !== id);
        state.pagination.total = Math.max(0, state.pagination.total - 1);
        if (state.item?.id === id) {
          state.item = null;
        }
      });
    }
  }))
);
