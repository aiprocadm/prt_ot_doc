import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { normalizeCompanyRead } from "@/api/companiesApi";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState, PaginationParams } from "@/stores/types";
import type { ApiError, PaginatedResponse } from "@/types/dto/common";
import type {
  CompanyDto,
  CompanyFiltersDto,
  UpdateCompanyDto,
} from "@/types/dto/companies";

type LegacyCompaniesResponse = {
  items?: unknown;
  total?: number;
  limit?: number;
  offset?: number;
  pagination?: {
    page?: number;
    page_size?: number;
    total?: number;
  } | null;
};

interface CompaniesState extends PaginatedState<CompanyDto, CompanyFiltersDto> {
  list: (
    params?: Partial<CompanyFiltersDto> & PaginationParams,
  ) => Promise<void>;
  getById: (id: string) => Promise<CompanyDto | null>;
  create: (payload: UpdateCompanyDto) => Promise<CompanyDto>;
  update: (id: string, payload: UpdateCompanyDto) => Promise<CompanyDto>;
  remove: (id: string) => Promise<void>;
  setFilters: (filters: Partial<CompanyFiltersDto>) => void;
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
  reset: () => void;
}

const createInitialState = () => ({
  items: [] as CompanyDto[],
  item: null as CompanyDto | null,
  filters: {} as CompanyFiltersDto,
  pagination: defaultPagination(),
  loading: false,
  error: null as ApiError | null,
});

const isPositiveNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value > 0;

const isNonNegativeNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0;

const normalizeCompaniesResponse = (
  payload: PaginatedResponse<CompanyDto> | LegacyCompaniesResponse,
  fallback: ReturnType<typeof defaultPagination>,
) => {
  const items = Array.isArray(payload?.items)
    ? payload.items.filter((item): item is CompanyDto =>
        Boolean(item && typeof item === "object" && "id" in item),
      )
    : [];
  const pagination = payload.pagination ?? null;
  const legacyLimit = (payload as LegacyCompaniesResponse).limit;
  const legacyOffset = (payload as LegacyCompaniesResponse).offset;
  const legacyTotal = (payload as LegacyCompaniesResponse).total;
  const pageSizeFromPayload = pagination?.page_size;
  const pageFromPayload = pagination?.page;
  const totalFromPayload = pagination?.total;

  const pageSize: number = isPositiveNumber(pageSizeFromPayload)
    ? pageSizeFromPayload
    : isPositiveNumber(legacyLimit)
      ? legacyLimit
      : fallback.page_size;
  const offset: number = isNonNegativeNumber(legacyOffset)
    ? legacyOffset
    : (fallback.page - 1) * pageSize;
  const page: number = isPositiveNumber(pageFromPayload)
    ? pageFromPayload
    : Math.floor(offset / Math.max(pageSize, 1)) + 1;
  const total: number = isNonNegativeNumber(totalFromPayload)
    ? totalFromPayload
    : isNonNegativeNumber(legacyTotal)
      ? legacyTotal
      : items.length;

  return {
    items,
    pagination: {
      page,
      page_size: pageSize,
      total,
    },
  };
};

export const useCompaniesStore = create<CompaniesState>()(
  immer((set, get) => ({
    ...createInitialState(),
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
      const query = { ...get().filters, ...params, limit, offset };
      try {
        const { data } = await apiClient.get<
          PaginatedResponse<CompanyDto> | LegacyCompaniesResponse
        >("/companies", { params: query });
        const normalized = normalizeCompaniesResponse(data, get().pagination);
        set((state) => {
          state.items = normalized.items.map((row) =>
            normalizeCompanyRead(row),
          );
          state.pagination = normalized.pagination;
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
        const { data } = await apiClient.get<unknown>(`/companies/${id}`);
        const row = normalizeCompanyRead(data);
        set((state) => {
          state.item = row;
        });
        return row;
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
        return null;
      }
    },
    create: async (payload) => {
      const { data } = await apiClient.post<unknown>("/companies", payload);
      const row = normalizeCompanyRead(data);
      set((state) => {
        state.items.unshift(row);
        state.pagination.total += 1;
      });
      return row;
    },
    update: async (id, payload) => {
      const { data } = await apiClient.patch<unknown>(
        `/companies/${id}`,
        payload,
      );
      const row = normalizeCompanyRead(data);
      set((state) => {
        state.items = state.items.map((company) =>
          company.id === id ? row : company,
        );
        if (state.item?.id === id) {
          state.item = row;
        }
      });
      return row;
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
    },
  })),
);
