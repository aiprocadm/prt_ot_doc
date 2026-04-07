import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { ApiError, PaginatedResponse } from "@/types/dto/common";
import type { TaskDto, TaskFiltersDto } from "@/types/dto/tasks";

interface TasksState extends PaginatedState<TaskDto, TaskFiltersDto> {
  list: (params?: Partial<TaskFiltersDto>) => Promise<void>;
  getById: (id: string) => Promise<TaskDto | null>;
  createTask: (payload: {
    title: string;
    description?: string | null;
    due_at?: string | null;
    priority?: TaskDto["priority"];
  }) => Promise<TaskDto | null>;
  setFilters: (filters: Partial<TaskFiltersDto>) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  patchTask: (id: string, payload: Partial<Pick<TaskDto, "status" | "assignee_id" | "due_at">>) => Promise<TaskDto | null>;
  updateTask: (task: TaskDto) => void;
  reset: () => void;
}

export const useTasksStore = create<TasksState>()(
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
        const { data } = await apiClient.get<PaginatedResponse<TaskDto>>("/tasks", { params: query });
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
        const { data } = await apiClient.get<TaskDto>(`/tasks/${id}`);
        set((state) => {
          state.item = data;
          const index = state.items.findIndex((task) => task.id === id);
          if (index >= 0) state.items[index] = data;
        });
        return data;
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
        return null;
      }
    },
    createTask: async (payload) => {
      try {
        const { data } = await apiClient.post<TaskDto>("/tasks", payload);
        get().updateTask(data);
        set((state) => {
          state.pagination.total += 1;
          state.error = null;
        });
        return data;
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
        return null;
      }
    },
    patchTask: async (id, payload) => {
      try {
        const { data } = await apiClient.patch<TaskDto>(`/tasks/${id}`, payload);
        get().updateTask(data);
        return data;
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
        return null;
      }
    },
    updateTask: (task) => {
      set((state) => {
        const index = state.items.findIndex((item) => item.id === task.id);
        if (index >= 0) {
          state.items[index] = task;
        } else {
          state.items.unshift(task);
        }
        if (state.item?.id === task.id) state.item = task;
      });
    }
  }))
);
