import { useEffect, useMemo, useState } from "react";

import { useDebounce } from "@/hooks/useDebounce";

type LocalRegistryOptions<TItem> = {
  items: TItem[];
  match: (item: TItem, query: string) => boolean;
  initialPageSize?: number;
  /**
   * Серверный отбор (срез-123). Экран показывает первую страницу реестра, а
   * ищет по ней же — пока строк мало, разницы нет; на большом реестре
   * существующая запись просто «не находится», и человек заводит дубль.
   *
   * Если функция передана, непустой запрос уходит на сервер, а локальный
   * отбор ВЫКЛЮЧАЕТСЯ: сервер умеет искать по полям, которых нет на экране
   * (например, по VIN), и местный фильтр спрятал бы найденное.
   */
  remoteSearch?: (query: string) => Promise<TItem[]>;
};

export const useLocalRegistry = <TItem>({
  items,
  match,
  initialPageSize = 10,
  remoteSearch,
}: LocalRegistryOptions<TItem>) => {
  const [pageIndex, setPageIndex] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);
  const [query, setQuery] = useState("");
  const [remoteItems, setRemoteItems] = useState<TItem[] | null>(null);
  const [searching, setSearching] = useState(false);

  const debouncedQuery = useDebounce(query, 400);

  useEffect(() => {
    if (!remoteSearch) return;
    const needle = debouncedQuery.trim();
    if (!needle) {
      setRemoteItems(null);
      setSearching(false);
      return;
    }
    let cancelled = false;
    setSearching(true);
    void remoteSearch(needle)
      .then((rows) => {
        if (!cancelled) setRemoteItems(rows);
      })
      .catch(() => {
        // Сорвавшийся поиск не должен подсовывать старый ответ как новый:
        // пустой список честнее, чем чужие строки под свежим запросом.
        if (!cancelled) setRemoteItems([]);
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, remoteSearch]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return items;
    if (remoteSearch) {
      // Пока ответ сервера не пришёл, показываем то, что уже есть на руках,
      // отобранное локально: экран не должен мигать пустотой на каждой букве.
      return remoteItems ?? items.filter((item) => match(item, normalized));
    }
    return items.filter((item) => match(item, normalized));
  }, [items, match, query, remoteItems, remoteSearch]);

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
    searching,
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
