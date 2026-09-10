import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { ApiError } from "@/types/dto/common";
import type {
  NpaDto,
  NpaFiltersDto,
  NpaListResponseDto,
} from "@/types/dto/npa";

/**
 * Реестр НПА.
 *
 * Срез-141: `GET /npa` отдаёт ВЕСЬ реестр одним списком (`{ items, can_manage }`),
 * без страничной обёртки — прежний код клал `data.pagination` (undefined) в
 * состояние и ронял таблицу на первой же странице. Реестр общий и короткий
 * (десятки актов), поэтому поиск и страницы считаем на витрине.
 */
interface NpaState extends PaginatedState<NpaDto, NpaFiltersDto> {
  /** Полный ответ сервера; `items` — отфильтрованная страница из него. */
  all: NpaDto[];
  canManage: boolean;
  list: (params?: Partial<NpaFiltersDto>) => Promise<void>;
  setFilters: (filters: Partial<NpaFiltersDto>) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  reset: () => void;
}

const matches = (item: NpaDto, search: string | undefined): boolean => {
  const needle = (search ?? "").trim().toLowerCase();
  if (!needle) return true;
  return (
    item.code.toLowerCase().includes(needle) ||
    item.title.toLowerCase().includes(needle)
  );
};

const emptyState = () => ({
  all: [] as NpaDto[],
  canManage: false,
  items: [] as NpaDto[],
  item: null as NpaDto | null,
  filters: {} as NpaFiltersDto,
  pagination: defaultPagination(),
  loading: false,
  error: null as ApiError | null,
});

export const useNpaStore = create<NpaState>()(
  immer((set) => {
    const recompute = () => {
      set((state) => {
        const filtered = state.all.filter((item) =>
          matches(item, state.filters.search),
        );
        const { page, page_size } = state.pagination;
        state.pagination.total = filtered.length;
        state.items = filtered.slice((page - 1) * page_size, page * page_size);
      });
    };

    return {
      ...emptyState(),
      setFilters: (filters) => {
        set((state) => {
          state.filters = { ...state.filters, ...filters };
          state.pagination.page = 1;
        });
        recompute();
      },
      setPage: (page) => {
        set((state) => {
          state.pagination.page = page;
        });
        recompute();
      },
      setPageSize: (size) => {
        set((state) => {
          state.pagination.page_size = size;
          state.pagination.page = 1;
        });
        recompute();
      },
      reset: () => {
        set(() => emptyState());
      },
      list: async (params) => {
        set((state) => {
          state.loading = true;
          state.error = null;
          if (params) {
            state.filters = { ...state.filters, ...params };
          }
        });
        try {
          const { data } = await apiClient.get<NpaListResponseDto>("/npa");
          set((state) => {
            state.all = data.items;
            state.canManage = data.can_manage ?? false;
          });
          recompute();
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
    };
  }),
);
