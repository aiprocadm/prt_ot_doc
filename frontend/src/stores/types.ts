import type {
  ApiError,
  PaginatedResponse,
  PaginationDto,
} from "@/types/dto/common";

export interface PaginatedState<T, Filters = Record<string, unknown>> {
  items: T[];
  item?: T | null;
  filters: Filters;
  pagination: PaginationDto;
  loading: boolean;
  error?: ApiError | null;
}

export interface PaginationParams {
  page?: number;
  page_size?: number;
}

export type PaginatedFetcher<T> = (
  params?: PaginationParams,
) => Promise<PaginatedResponse<T>>;
