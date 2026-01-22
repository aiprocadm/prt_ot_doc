import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { ApiError, PaginatedResponse } from "@/types/dto/common";
import type { FileDto } from "@/types/dto/files";

interface FileFilters {
  search?: string;
  tag?: string;
}

interface FilesState extends PaginatedState<FileDto, FileFilters> {
  list: (params?: Partial<FileFilters>) => Promise<void>;
  upload: (file: File, meta?: { description?: string; tags?: string[] }) => Promise<FileDto>;
  remove: (id: string) => Promise<void>;
  setFilters: (filters: Partial<FileFilters>) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
}

export const useFilesStore = create<FilesState>()(
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
        const { data } = await apiClient.get<PaginatedResponse<FileDto>>("/files", { params: query });
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
    upload: async (file, meta) => {
      const formData = new FormData();
      formData.append("file", file);
      if (meta?.description) formData.append("description", meta.description);
      if (meta?.tags) meta.tags.forEach((tag) => formData.append("tags", tag));
      const { data } = await apiClient.post<FileDto>("/files", formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      set((state) => {
        state.items.unshift(data);
        state.pagination.total += 1;
      });
      return data;
    },
    remove: async (id) => {
      await apiClient.delete(`/files/${id}`);
      set((state) => {
        state.items = state.items.filter((file) => file.id !== id);
        state.pagination.total = Math.max(0, state.pagination.total - 1);
      });
    }
  }))
);
