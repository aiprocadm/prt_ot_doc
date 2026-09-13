import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { PaginatedResponse } from "@/types/dto/common";
import type { FileDto } from "@/types/dto/files";
import { normalizeError } from "@/utils/apiFormErrors";

interface FileFilters {
  search?: string;
  tag?: string;
}

// Срез-157: из хранилища убран `upload` — он звал `POST /files`, ручки с
// таким путём у сервера нет, и ни один экран его не вызывал. Файлы
// грузит `FileUploader` по подписанной ссылке (инициация → PUT в
// хранилище → подтверждение).
interface FilesState extends PaginatedState<FileDto, FileFilters> {
  list: (params?: Partial<FileFilters>) => Promise<void>;
  remove: (id: string) => Promise<void>;
  setFilters: (filters: Partial<FileFilters>) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  reset: () => void;
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
    reset: () => {
      set(() => ({
        items: [],
        item: null,
        filters: {},
        pagination: defaultPagination(),
        loading: false,
        error: null,
      }));
    },
    list: async (params) => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      const query = {
        ...get().filters,
        ...params,
        page: get().pagination.page,
        page_size: get().pagination.page_size,
      };
      try {
        const { data } = await apiClient.get<PaginatedResponse<FileDto>>(
          "/files",
          { params: query },
        );
        set((state) => {
          state.items = data.items;
          state.pagination = data.pagination;
        });
      } catch (error) {
        set((state) => {
          state.error = normalizeError(error);
        });
      } finally {
        set((state) => {
          state.loading = false;
        });
      }
    },
    remove: async (id) => {
      try {
        await apiClient.delete(`/files/${id}`);
        set((state) => {
          state.items = state.items.filter((file) => file.id !== id);
          state.pagination.total = Math.max(0, state.pagination.total - 1);
        });
      } catch (error) {
        set((state) => {
          state.error = normalizeError(error);
        });
        throw error;
      }
    },
  })),
);
