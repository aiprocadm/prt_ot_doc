import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { ApiError, PaginatedResponse } from "@/types/dto/common";
import type { CompanyDto, CompanyFiltersDto, UpdateCompanyDto } from "@/types/dto/companies";

interface CompaniesState extends PaginatedState<CompanyDto, CompanyFiltersDto> {
  list: (params?: Partial<CompanyFiltersDto>) => Promise<void>;
  getById: (id: string) => Promise<CompanyDto | null>;
  create: (payload: UpdateCompanyDto) => Promise<CompanyDto>;
  update: (id: string, payload: UpdateCompanyDto) => Promise<CompanyDto>;
  remove: (id: string) => Promise<void>;
  setFilters: (filters: Partial<CompanyFiltersDto>) => void;
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
}

export const useCompaniesStore = create<CompaniesState>()(
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
    setPageSize: (pageSize) => {
      set((state) => {
        state.pagination.page_size = pageSize;
        state.pagination.page = 1;
      });
    },
    list: async (params) => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      const query = { ...get().filters, ...params, page: get().pagination.page, page_size: get().pagination.page_size };
      try {
        const { data } = await apiClient.get<PaginatedResponse<CompanyDto>>("/companies", { params: query });
        set((state) => {
          state.items = data.items;
          state.pagination = data.pagination;
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
    getById: async (id: string) => {
      try {
        const { data } = await apiClient.get<CompanyDto>(`/companies/${id}`);
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
      const { data } = await apiClient.post<CompanyDto>("/companies", payload);
      set((state) => {
        state.items.unshift(data);
        state.pagination.total += 1;
      });
      return data;
    },
    update: async (id, payload) => {
      const { data } = await apiClient.put<CompanyDto>(`/companies/${id}`, payload);
      set((state) => {
        state.items = state.items.map((company) => (company.id === id ? data : company));
        if (state.item?.id === id) {
          state.item = data;
        }
      });
      return data;
    },
    remove: async (id) => {
      await apiClient.delete(`/companies/${id}`);
      set((state) => {
        state.items = state.items.filter((company) => company.id !== id);
        state.pagination.total = Math.max(0, state.pagination.total - 1);
        if (state.item?.id === id) {
          state.item = null;
        }
      });
    }
  }))
);
