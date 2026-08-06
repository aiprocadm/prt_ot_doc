import { useCallback, useMemo, useState } from "react";

export interface PaginationState {
  page: number;
  pageSize: number;
  total: number;
}

export const usePagination = (
  initial: PaginationState = { page: 1, pageSize: 10, total: 0 },
) => {
  const [pagination, setPagination] = useState(initial);

  const setPage = useCallback((page: number) => {
    setPagination((prev) => ({ ...prev, page }));
  }, []);

  const setPageSize = useCallback((pageSize: number) => {
    setPagination((prev) => ({ ...prev, pageSize, page: 1 }));
  }, []);

  const setTotal = useCallback((total: number) => {
    setPagination((prev) => ({ ...prev, total }));
  }, []);

  return useMemo(
    () => ({
      pagination,
      setPage,
      setPageSize,
      setTotal,
    }),
    [pagination, setPage, setPageSize, setTotal],
  );
};
