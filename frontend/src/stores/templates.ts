import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { ApiError, PaginatedResponse } from "@/types/dto/common";
import type { TemplateDto, TemplateStatus, UpdateTemplateDto } from "@/types/dto/templates";

interface TemplateFilters {
  search?: string;
  status?: TemplateStatus;
  document_type?: string;
  company_id?: string;
  site_id?: string;
}

interface TemplatesState extends PaginatedState<TemplateDto, TemplateFilters> {
  list: (params?: Partial<TemplateFilters>) => Promise<void>;
  getById: (id: string) => Promise<TemplateDto | null>;
  create: (payload: UpdateTemplateDto) => Promise<TemplateDto>;
  update: (id: string, payload: UpdateTemplateDto) => Promise<TemplateDto>;
  remove: (id: string) => Promise<void>;
  activateVersion: (templateId: string, versionId: string) => Promise<TemplateDto>;
  setFilters: (filters: Partial<TemplateFilters>) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  reset: () => void;
}

export const useTemplatesStore = create<TemplatesState>()(
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
        const { data } = await apiClient.get<PaginatedResponse<TemplateDto> | { items: TemplateDto[]; total: number }>("/templates", { params: query });
        set((state) => {
          state.items = data.items;
          state.pagination = "pagination" in data
            ? data.pagination
            : { page: get().pagination.page, page_size: get().pagination.page_size, total: data.total };
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
        const { data } = await apiClient.get<TemplateDto>(`/templates/${id}`);
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
      const { data } = await apiClient.post<TemplateDto>("/templates/catalog", payload);
      set((state) => {
        state.items.unshift(data);
        state.pagination.total += 1;
      });
      return data;
    },
    update: async (id, payload) => {
      const { data } = await apiClient.patch<TemplateDto>(`/templates/${id}`, payload);
      set((state) => {
        state.items = state.items.map((template) => (template.id === id ? data : template));
        if (state.item?.id === id) state.item = data;
      });
      return data;
    },
    activateVersion: async (templateId, versionId) => {
      const { data } = await apiClient.patch<TemplateDto>(`/templates/${templateId}`, { current_version_id: versionId });
      set((state) => {
        state.items = state.items.map((template) => (template.id === templateId ? data : template));
        if (state.item?.id === templateId) state.item = data;
      });
      return data;
    },
    remove: async (id) => {
      await apiClient.delete(`/templates/${id}`);
      set((state) => {
        state.items = state.items.filter((template) => template.id !== id);
        state.pagination.total = Math.max(0, state.pagination.total - 1);
        if (state.item?.id === id) state.item = null;
      });
    }
  }))
);
