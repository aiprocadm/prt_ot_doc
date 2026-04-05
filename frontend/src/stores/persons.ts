import { create } from "zustand";
import { immer } from "zustand/middleware/immer";

import { apiClient } from "@/api/client";
import { buildPersonCreateBody, buildPersonPatchBody, normalizePersonRead } from "@/api/personsApi";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { ApiError } from "@/types/dto/common";
import type { PersonDto, PersonStatus } from "@/types/dto/persons";
import type { PersonFormValues } from "@/types/forms/persons";

type PersonListResponse = { items: unknown[]; total: number };

interface PersonFilters {
  search?: string;
  status?: PersonStatus;
}

interface PersonsState extends PaginatedState<PersonDto, PersonFilters> {
  /** Увеличивается при create/update/delete — карточка компании перезагружает список сотрудников. */
  personsRegistryRevision: number;
  list: (params?: Partial<PersonFilters>) => Promise<void>;
  getById: (id: string) => Promise<PersonDto | null>;
  create: (payload: PersonFormValues) => Promise<PersonDto>;
  update: (id: string, payload: PersonFormValues) => Promise<PersonDto>;
  remove: (id: string) => Promise<void>;
  setFilters: (filters: Partial<PersonFilters>) => void;
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
  reset: () => void;
}

export const usePersonsStore = create<PersonsState>()(
  immer((set, get) => ({
    items: [],
    item: null,
    filters: {},
    pagination: defaultPagination(),
    loading: false,
    error: null,
    personsRegistryRevision: 0,
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
    reset: () => {
      set(() => ({
        items: [],
        item: null,
        filters: {},
        pagination: defaultPagination(),
        loading: false,
        error: null,
        personsRegistryRevision: 0
      }));
    },
    list: async (params) => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      const { page, page_size: pageSize } = get().pagination;
      const rawLimit = Number(pageSize);
      const limit = Math.min(200, Math.max(1, Number.isFinite(rawLimit) ? rawLimit : 10));
      const rawPage = Number(page);
      const safePage = Number.isFinite(rawPage) && rawPage >= 1 ? Math.floor(rawPage) : 1;
      const offset = Math.max(0, (safePage - 1) * limit);
      const query = { ...get().filters, ...params, limit, offset };
      try {
        const { data } = await apiClient.get<PersonListResponse>("/persons", { params: query });
        const items = (data.items ?? []).map((row) => normalizePersonRead(row));
        set((state) => {
          state.items = items;
          state.pagination = {
            page,
            page_size: pageSize,
            total: data.total ?? items.length
          };
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
        const { data } = await apiClient.get<unknown>(`/persons/${id}`);
        const normalized = normalizePersonRead(data);
        set((state) => {
          state.item = normalized;
        });
        return normalized;
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
        return null;
      }
    },
    create: async (payload) => {
      const body = buildPersonCreateBody(payload);
      const { data } = await apiClient.post<unknown>("/persons", body);
      const normalized = normalizePersonRead(data);
      set((state) => {
        state.items.unshift(normalized);
        state.pagination.total += 1;
        state.personsRegistryRevision += 1;
      });
      return normalized;
    },
    update: async (id, payload) => {
      const body = buildPersonPatchBody(payload);
      const { data } = await apiClient.patch<unknown>(`/persons/${id}`, body);
      const normalized = normalizePersonRead(data);
      set((state) => {
        state.items = state.items.map((person) => (person.id === id ? normalized : person));
        if (state.item?.id === id) {
          state.item = normalized;
        }
        state.personsRegistryRevision += 1;
      });
      return normalized;
    },
    remove: async (id) => {
      await apiClient.delete(`/persons/${id}`);
      set((state) => {
        state.items = state.items.filter((person) => person.id !== id);
        state.pagination.total = Math.max(0, state.pagination.total - 1);
        if (state.item?.id === id) state.item = null;
        state.personsRegistryRevision += 1;
      });
    }
  }))
);
