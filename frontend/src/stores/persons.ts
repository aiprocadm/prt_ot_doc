import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { ApiError, PaginatedResponse } from "@/types/dto/common";
import type { PersonDto, PersonStatus, UpdatePersonDto } from "@/types/dto/persons";

interface PersonFilters {
  search?: string;
  status?: PersonStatus;
}

interface PersonsState extends PaginatedState<PersonDto, PersonFilters> {
  list: (params?: Partial<PersonFilters>) => Promise<void>;
  getById: (id: string) => Promise<PersonDto | null>;
  create: (payload: UpdatePersonDto) => Promise<PersonDto>;
  update: (id: string, payload: UpdatePersonDto) => Promise<PersonDto>;
  remove: (id: string) => Promise<void>;
  setFilters: (filters: Partial<PersonFilters>) => void;
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
}

export const usePersonsStore = create<PersonsState>()(
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
        const { data } = await apiClient.get<PaginatedResponse<PersonDto>>("/persons", { params: query });
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
        const { data } = await apiClient.get<PersonDto>(`/persons/${id}`);
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
      const { data } = await apiClient.post<PersonDto>("/persons", payload);
      set((state) => {
        state.items.unshift(data);
        state.pagination.total += 1;
      });
      return data;
    },
    update: async (id, payload) => {
      const { data } = await apiClient.put<PersonDto>(`/persons/${id}`, payload);
      set((state) => {
        state.items = state.items.map((person) => (person.id === id ? data : person));
        if (state.item?.id === id) {
          state.item = data;
        }
      });
      return data;
    },
    remove: async (id) => {
      await apiClient.delete(`/persons/${id}`);
      set((state) => {
        state.items = state.items.filter((person) => person.id !== id);
        state.pagination.total = Math.max(0, state.pagination.total - 1);
        if (state.item?.id === id) state.item = null;
      });
    }
  }))
);
