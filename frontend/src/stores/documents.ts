import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/api/client";
import { defaultPagination } from "@/stores/helpers";
import type { PaginatedState } from "@/stores/types";
import type { ApiError, PaginatedResponse } from "@/types/dto/common";
import type { DocumentDto, DocumentFiltersDto } from "@/types/dto/documents";
import { normalizeError } from "@/utils/apiFormErrors";

type LegacyDocumentsResponse = {
  items?: unknown;
  pagination?: {
    page?: number;
    page_size?: number;
    total?: number;
  } | null;
  total?: number;
  limit?: number;
  offset?: number;
};

type DocumentsResponse = PaginatedResponse<DocumentDto> | LegacyDocumentsResponse;

interface GenerateDocumentPayload {
  template_code: string;
  template_version: number;
  template_id?: string;
  company_id: string;
  person_id?: string;
  data?: Record<string, unknown>;
}

interface GenerationAcceptedResponse {
  task_id: string;
  status_url: string;
  document_version_id?: string | null;
}

interface GenerationTaskStatus {
  task_id: string;
  status: "queued" | "running" | "done" | "error" | string;
  document_id?: string | null;
  document_version_id?: string | null;
  error?: string | null;
  metadata?: Record<string, unknown> | null;
}

interface DocumentsState extends PaginatedState<DocumentDto, DocumentFiltersDto> {
  list: (params?: Partial<DocumentFiltersDto>) => Promise<void>;
  getById: (id: string) => Promise<DocumentDto | null>;
  setFilters: (filters: Partial<DocumentFiltersDto>) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  download: (id: string) => Promise<Blob>;
  refreshStatus: (id: string) => Promise<DocumentDto | null>;
  generateDocument: (
    payload: GenerateDocumentPayload,
    idempotencyKey: string
  ) => Promise<GenerationAcceptedResponse>;
  getGenerationStatus: (taskId: string) => Promise<GenerationTaskStatus>;
  reset: () => void;
}

const isPositiveNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value > 0;

const isNonNegativeNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0;

const isPaginationRecord = (value: unknown): value is { page?: unknown; page_size?: unknown; total?: unknown } =>
  typeof value === "object" && value !== null;

const hasLegacyWindow = (value: DocumentsResponse): value is LegacyDocumentsResponse =>
  "limit" in value || "offset" in value || "total" in value;

const normalizeDocumentsResponse = (
  payload: DocumentsResponse,
  fallback: ReturnType<typeof defaultPagination>
) => {
  const items = Array.isArray(payload?.items) ? (payload.items as DocumentDto[]) : [];
  const pagination = isPaginationRecord(payload.pagination) ? payload.pagination : null;
  const pageSize = isPositiveNumber(pagination?.page_size)
    ? pagination.page_size
    : hasLegacyWindow(payload) && isPositiveNumber(payload.limit)
      ? payload.limit
      : fallback.page_size;
  const offset = hasLegacyWindow(payload) && isNonNegativeNumber(payload.offset) ? payload.offset : (fallback.page - 1) * pageSize;
  const page = isPositiveNumber(pagination?.page)
    ? pagination.page
    : Math.floor(offset / Math.max(pageSize, 1)) + 1;
  const total = isNonNegativeNumber(pagination?.total)
    ? pagination.total
    : hasLegacyWindow(payload) && isNonNegativeNumber(payload.total)
      ? payload.total
      : items.length;

  return {
    items,
    pagination: {
      page,
      page_size: pageSize,
      total
    }
  };
};

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
        const { data } = await apiClient.get<DocumentsResponse>("/documents", { params: query });
        const normalized = normalizeDocumentsResponse(data, get().pagination);
        set((state) => {
          state.items = normalized.items;
          state.pagination = normalized.pagination;
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
    getById: async (id) => {
      try {
        const { data } = await apiClient.get<DocumentDto>(`/documents/${id}`);
        set((state) => {
          state.item = data;
        });
        return data;
      } catch (error) {
        set((state) => {
          state.error = normalizeError(error);
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
          state.error = normalizeError(error);
        });
        return null;
      }
    },
    generateDocument: async (payload, idempotencyKey) => {
      const response = await apiClient.post<GenerationAcceptedResponse>("/documents/generate", payload, {
        headers: {
          "Idempotency-Key": idempotencyKey
        }
      });
      return response.data;
    },
    getGenerationStatus: async (taskId) => {
      const response = await apiClient.get<GenerationTaskStatus>(`/documents/tasks/${taskId}`);
      return response.data;
    }
  }))
);
