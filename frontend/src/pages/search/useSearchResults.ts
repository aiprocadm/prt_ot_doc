import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSearch, type SearchItem } from "@/api/search";
import type { ApiError } from "@/types/dto/common";
import type { SearchFacets } from "./types";
import type { SearchType } from "@/api/search";

type Params = {
  query: string;
  activeTypes: SearchType[];
  status: string;
  companyId: string;
  siteId: string;
  projectId: string;
  riskLevel: string;
  /** Вызывается после успешной загрузки результатов (например, обновить recent/saved в сайдбаре). */
  onSearchSuccess?: () => void;
};

export const useSearchResults = ({ query, activeTypes, status, companyId, siteId, projectId, riskLevel, onSearchSuccess }: Params) => {
  const [items, setItems] = useState<SearchItem[]>([]);
  const [facets, setFacets] = useState<SearchFacets>({});
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const searchRequestId = useRef(0);
  const loadMoreRequestId = useRef(0);
  const loadMoreInFlight = useRef(false);
  const activeLoadMoreController = useRef<AbortController | null>(null);
  const onSearchSuccessRef = useRef(onSearchSuccess);
  onSearchSuccessRef.current = onSearchSuccess;

  useEffect(() => {
    if (!query.trim()) {
      setItems([]);
      setFacets({});
      setNextCursor(null);
      setError(null);
      return;
    }

    const requestId = ++searchRequestId.current;
    const controller = new AbortController();

    setLoading(true);
    setError(null);

    fetchSearch(
      {
        q: query,
        types: activeTypes,
        status: status || undefined,
        company_id: companyId || undefined,
        site_id: siteId || undefined,
        project_id: projectId || undefined,
        risk_level: riskLevel || undefined,
      },
      { signal: controller.signal },
    )
      .then((data) => {
        if (searchRequestId.current !== requestId) return;
        setItems(data.items);
        setFacets(data.facets ?? {});
        setNextCursor(data.next_cursor ?? null);
        onSearchSuccessRef.current?.();
      })
      .catch((err) => {
        if (controller.signal.aborted || searchRequestId.current !== requestId) return;
        const apiError = (err as ApiError) ?? { status: 500, message: "Не удалось загрузить результаты поиска" };
        setError({ status: apiError.status ?? 500, message: apiError.message ?? "Не удалось загрузить результаты поиска" });
        setItems([]);
        setFacets({});
        setNextCursor(null);
      })
      .finally(() => {
        if (searchRequestId.current !== requestId) return;
        setLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [query, activeTypes, status, companyId, siteId, projectId, riskLevel, reloadNonce]);

  const reload = () => setReloadNonce((prev) => prev + 1);

  const loadMore = useCallback(async () => {
    if (!nextCursor || loadMoreInFlight.current) return;

    const requestId = ++loadMoreRequestId.current;
    const controller = new AbortController();
    activeLoadMoreController.current?.abort();
    activeLoadMoreController.current = controller;

    loadMoreInFlight.current = true;
    setLoadingMore(true);
    try {
      const data = await fetchSearch(
        {
          q: query,
          types: activeTypes,
          cursor: nextCursor,
          status: status || undefined,
          company_id: companyId || undefined,
          site_id: siteId || undefined,
          project_id: projectId || undefined,
          risk_level: riskLevel || undefined,
        },
        { signal: controller.signal },
      );
      if (loadMoreRequestId.current !== requestId) return;
      setItems((prev) => [...prev, ...data.items]);
      setNextCursor(data.next_cursor ?? null);
      setError(null);
    } catch (err) {
      if (controller.signal.aborted || loadMoreRequestId.current !== requestId) return;
      const apiError = (err as ApiError) ?? { status: 500, message: "Не удалось загрузить дополнительные результаты" };
      setError({ status: apiError.status ?? 500, message: apiError.message ?? "Не удалось загрузить дополнительные результаты" });
    } finally {
      if (loadMoreRequestId.current === requestId) {
        loadMoreInFlight.current = false;
        setLoadingMore(false);
      }
    }
  }, [activeTypes, companyId, nextCursor, projectId, query, riskLevel, siteId, status]);

  return {
    items,
    facets,
    nextCursor,
    loading,
    loadingMore,
    error,
    loadMore,
    reload,
  };
};
