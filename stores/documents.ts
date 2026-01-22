import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { ApiError, PaginatedResponse } from "@/types/dto/common";
import type { DocumentDto, DocumentFiltersDto } from "@/types/dto/documents";

interface DocumentsState extends PaginatedState<DocumentDto, DocumentFiltersDto> {
  list: (params?: Partial<DocumentFiltersDto>) => Promise<void>;
  getById: (id: string) => Promise<DocumentDto | null>;
  setFilters: (filters: Partial<DocumentFiltersDto>) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  download: (id: string) => Promise<Blob>;
  refreshStatus: (id: string) => Promise<DocumentDto | null>;
}

export const useDocumentsStore = create<DocumentsState>()(
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
    list: async (params) => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      const query = { ...get().filters, ...params, page: get().pagination.page, page_size: get().pagination.page_size };
      try {
        const { data } = await apiClient.get<PaginatedResponse<DocumentDto>>("/documents", { params: query });
        set((state) => {
          state.items = data.items;
          state.pagination = data.pagination;
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
        const { data } = await apiClient.get<DocumentDto>(`/documents/${id}`);
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
    download: async (id) => {
      const { data } = await apiClient.get<Blob>(`/documents/${id}/download`, {
        responseType: "blob"
      });
      return data;
    },
    refreshStatus: async (id) => {
      try {
        const { data } = await apiClient.get<DocumentDto>(`/documents/${id}/status`);
        set((state) => {
          state.items = state.items.map((doc) => (doc.id === id ? data : doc));
          if (state.item?.id === id) state.item = data;
        });
        return data;
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
        return null;
      }
    }
  }))
);
