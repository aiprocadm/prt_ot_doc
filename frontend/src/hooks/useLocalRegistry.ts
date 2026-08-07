import { useMemo, useState } from "react";

type LocalRegistryOptions<TItem> = {
  items: TItem[];
  match: (item: TItem, query: string) => boolean;
  initialPageSize?: number;
};

export const useLocalRegistry = <TItem>({
  items,
  match,
  initialPageSize = 10,
}: LocalRegistryOptions<TItem>) => {
  const [pageIndex, setPageIndex] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) => match(item, normalized));
  }, [items, match, query]);

  const pagedItems = useMemo(() => {
    const offset = (pageIndex - 1) * pageSize;
    return filtered.slice(offset, offset + pageSize);
  }, [filtered, pageIndex, pageSize]);

  const onSearchChange = (value: string) => {
    setQuery(value);
    setPageIndex(1);
  };

  const onPageChange = (nextPage: number) => {
    setPageIndex(nextPage);
  };

  const onPageSizeChange = (nextSize: number) => {
    setPageSize(nextSize);
    setPageIndex(1);
  };

  return {
    query,
    filtered,
    pagedItems,
    pageIndex,
    pageSize,
    total: filtered.length,
    onSearchChange,
    onPageChange,
    onPageSizeChange,
  };
};
