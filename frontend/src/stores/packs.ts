import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { ApiError, PaginatedResponse } from "@/types/dto/common";
import type { PackDto, PackGenerationPayload, PackPreset } from "@/types/dto/packs";

interface PackFilters {
  search?: string;
  preset?: PackPreset;
  status?: PackDto["status"];
}

interface PacksState extends PaginatedState<PackDto, PackFilters> {
  list: (params?: Partial<PackFilters>) => Promise<void>;
  getById: (id: string) => Promise<PackDto | null>;
  create: (payload: PackGenerationPayload) => Promise<PackDto>;
  setFilters: (filters: Partial<PackFilters>) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  reset: () => void;
}

type LegacyPaginationMeta = {
  page?: number;
  per_page?: number;
  total?: number;
};

type LegacyPackListResponse = {
  data?: PackDto[];
  meta?: LegacyPaginationMeta;
};

const toPackListPayload = (
  payload: PaginatedResponse<PackDto> | LegacyPackListResponse | null | undefined
): PaginatedResponse<PackDto> => {
  if (payload && Array.isArray((payload as PaginatedResponse<PackDto>).items)) {
    return payload as PaginatedResponse<PackDto>;
  }

  const legacy = (payload ?? {}) as LegacyPackListResponse;
  const items = Array.isArray(legacy.data) ? legacy.data : [];
  const meta = legacy.meta ?? {};
  return {
    items,
    pagination: {
      page: typeof meta.page === "number" ? meta.page : 1,
      page_size: typeof meta.per_page === "number" ? meta.per_page : items.length || 20,
      total: typeof meta.total === "number" ? meta.total : items.length
    }
  };
};

export const usePacksStore = create<PacksState>()(
  immer((set, get) => ({
    items: [],
    item: null,
    filters: {},
    pagination: defaultPagination(),
    loading: false,
    error: null,
    setFilters: (filters) => {
      set((state) => {
        state.filters = { ...state.filters, ...filters };
      });
    },
    setPage: (page) => {
      set((state) => {
        state.pagination.page = page;
      });
    },
    setPageSize: (size) => {
      set((state) => {
        state.pagination.page_size = size;
        state.pagination.page = 1;
      });
    },
    reset: () => {
      set(() => ({
        items: [],
        item: null,
        filters: {},
        pagination: defaultPagination(),
        loading: false,
        error: null
      }));
    },
    list: async (params) => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      const query = { ...get().filters, ...params, page: get().pagination.page, page_size: get().pagination.page_size };
      try {
        const { data } = await apiClient.get<PaginatedResponse<PackDto> | LegacyPackListResponse>("/packs", { params: query });
        const normalized = toPackListPayload(data);
        set((state) => {
          state.items = normalized.items;
          state.pagination = normalized.pagination;
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
    getById: async (id) => {
      try {
        const { data } = await apiClient.get<PackDto>(`/packs/${id}`);
        set((state) => {
          state.item = data;
        });
        return data;
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
        return null;
      }
    },
    create: async (payload) => {
      const { data } = await apiClient.post<PackDto>("/packs", payload);
      set((state) => {
        state.items.unshift(data);
        state.pagination.total += 1;
      });
      return data;
    }
  }))
);
