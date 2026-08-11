import type { PaginationDto } from "@/types/dto/common";

export const defaultPagination = (): PaginationDto => ({
  page: 1,
  page_size: 10,
  total: 0,
});
