import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { usePagination } from "@/hooks/usePagination";

describe("usePagination", () => {
  it("меняет страницу и размер страницы", () => {
    const { result } = renderHook(() =>
      usePagination({ page: 2, pageSize: 20, total: 100 }),
    );

    act(() => result.current.setPage(3));
    expect(result.current.pagination.page).toBe(3);

    act(() => result.current.setPageSize(50));
    expect(result.current.pagination.pageSize).toBe(50);
    expect(result.current.pagination.page).toBe(1);

    act(() => result.current.setTotal(200));
    expect(result.current.pagination.total).toBe(200);
  });
});
