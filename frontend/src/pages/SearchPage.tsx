import { BookmarkPlus, Clock3, Filter, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  createSavedSearch,
  deleteSavedSearch,
  fetchRecentSearches,
  fetchSavedSearches,
  fetchSearch,
  type SavedSearchItem,
  type SearchItem,
  type SearchType
} from "@/api/search";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/useDebounce";
import type { ApiError } from "@/types/dto/common";

const tabs: Array<SearchType | "tasks" | "npa" | "contracts" | "orders"> = ["documents", "files", "people", "sites", "incidents", "inspections", "risk", "ppe", "training", "jobs", "templates", "tasks", "npa", "contracts", "orders"];

type Facets = {
  type_counts?: Record<string, number>;
  status_counts?: Record<string, number>;
  company_counts?: Record<string, number>;
  site_counts?: Record<string, number>;
  project_counts?: Record<string, number>;
  risk_level_counts?: Record<string, number>;
};

const isExternalLink = (link: string) => /^https?:\/\//i.test(link);

const SearchPage = () => {
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState<SearchItem[]>([]);
  const [facets, setFacets] = useState<Facets>({});
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [recent, setRecent] = useState<Array<{ id: string; q: string; types: string[] }>>([]);
  const [saved, setSaved] = useState<SavedSearchItem[]>([]);
  const searchRequestId = useRef(0);
  const loadMoreRequestId = useRef(0);
  const loadMoreInFlight = useRef(false);

  const q = params.get("q") ?? "";
  const debouncedQ = useDebounce(q, 350);
  const type = (params.get("type") as SearchType | "tasks" | "npa" | "contracts" | "orders" | null) ?? "documents";
  const status = params.get("status") ?? "";
  const companyId = params.get("company_id") ?? "";
  const siteId = params.get("site_id") ?? "";
  const projectId = params.get("project_id") ?? "";
  const riskLevel = params.get("risk_level") ?? "";

  const loadMemory = async () => {
    const [recentItems, savedItems] = await Promise.all([fetchRecentSearches(), fetchSavedSearches()]);
    setRecent(recentItems);
    setSaved(savedItems);
  };

  const patchParams = (patch: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([key, value]) => {
      if (value && value.trim()) next.set(key, value);
      else next.delete(key);
    });
    setParams(next);
  };

  const activeTypes = useMemo(() => (type ? [type] : tabs) as SearchType[], [type]);
  const activeFilterCount = useMemo(() => [status, companyId, siteId, projectId, riskLevel].filter(Boolean).length, [status, companyId, siteId, projectId, riskLevel]);

  useEffect(() => {
    void loadMemory().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!debouncedQ.trim()) {
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
        q: debouncedQ,
        types: activeTypes,
        status: status || undefined,
        company_id: companyId || undefined,
        site_id: siteId || undefined,
        project_id: projectId || undefined,
        risk_level: riskLevel || undefined
      },
      { signal: controller.signal }
    )
      .then((data) => {
        if (searchRequestId.current !== requestId) return;
        setItems(data.items);
        setFacets(data.facets ?? {});
        setNextCursor(data.next_cursor ?? null);
        void loadMemory();
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
  }, [debouncedQ, activeTypes, status, companyId, siteId, projectId, riskLevel, reloadNonce]);

  const loadMore = async () => {
    if (!nextCursor || loadMoreInFlight.current) return;

    const requestId = ++loadMoreRequestId.current;
    const controller = new AbortController();

    loadMoreInFlight.current = true;
    setLoadingMore(true);

    try {
      const data = await fetchSearch(
        {
          q: debouncedQ,
          types: activeTypes,
          cursor: nextCursor,
          status: status || undefined,
          company_id: companyId || undefined,
          site_id: siteId || undefined,
          project_id: projectId || undefined,
          risk_level: riskLevel || undefined
        },
        { signal: controller.signal }
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
  };

  const saveCurrentSearch = async () => {
    if (!q.trim()) return;
    await createSavedSearch({
      name: `${q.trim()} · ${type}`,
      q: q.trim(),
      types: activeTypes,
      filters: {
        ...(status ? { status } : {}),
        ...(companyId ? { company_id: companyId } : {}),
        ...(siteId ? { site_id: siteId } : {}),
        ...(projectId ? { project_id: projectId } : {}),
        ...(riskLevel ? { risk_level: riskLevel } : {})
      }
    });
    await loadMemory();
  };

  const applySavedSearch = (item: SavedSearchItem | { q: string; types: string[]; filters?: Record<string, unknown> }) => {
    const next = new URLSearchParams();
    next.set("q", item.q);
    if (item.types[0]) next.set("type", item.types[0]);
    const filters = item.filters ?? {};
    if (typeof filters.status === "string") next.set("status", filters.status);
    if (typeof filters.company_id === "string") next.set("company_id", filters.company_id);
    if (typeof filters.site_id === "string") next.set("site_id", filters.site_id);
    if (typeof filters.project_id === "string") next.set("project_id", filters.project_id);
    if (typeof filters.risk_level === "string") next.set("risk_level", filters.risk_level);
    setParams(next);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Search Center</h1>
        <div className="rounded-full border px-3 py-1 text-xs text-muted-foreground">Активных фильтров: {activeFilterCount}</div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.4fr,0.8fr]">
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-4 py-6">
              <Input value={q} placeholder="Поиск по системе" onChange={(e) => patchParams({ q: e.target.value })} />
              <div className="flex flex-wrap gap-2">
                {tabs.map((tab) => (
                  <Button key={tab} variant={tab === type ? "default" : "outline"} size="sm" onClick={() => patchParams({ type: tab })}>
                    {tab} ({facets.type_counts?.[tab] ?? facets.type_counts?.[tab.replace(/s$/, "")] ?? 0})
                  </Button>
                ))}
                <Button variant="outline" size="sm" onClick={() => void saveCurrentSearch()}>
                  <BookmarkPlus className="mr-2 h-4 w-4" /> Сохранить поиск
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-base">
                <Filter className="h-4 w-4" /> Faceted filters
              </CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => patchParams({ status: undefined, company_id: undefined, site_id: undefined, project_id: undefined, risk_level: undefined })}
              >
                Сбросить
              </Button>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <div className="space-y-2">
                <label className="text-xs font-medium uppercase text-muted-foreground">Status</label>
                <select className="h-10 rounded-md border px-3" value={status} onChange={(event) => patchParams({ status: event.target.value || undefined })}>
                  <option value="">Все</option>
                  {Object.entries(facets.status_counts ?? {}).map(([key, value]) => (
                    <option key={key} value={key}>
                      {key} ({value})
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium uppercase text-muted-foreground">Company scope</label>
                <Input placeholder="company_id" value={companyId} onChange={(event) => patchParams({ company_id: event.target.value || undefined })} />
                <div className="text-xs text-muted-foreground">Facet IDs: {Object.keys(facets.company_counts ?? {}).slice(0, 5).join(", ") || "—"}</div>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium uppercase text-muted-foreground">Site scope</label>
                <Input placeholder="site_id" value={siteId} onChange={(event) => patchParams({ site_id: event.target.value || undefined })} />
                <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
                  {Object.entries(facets.site_counts ?? {})
                    .slice(0, 5)
                    .map(([key, value]) => (
                      <button type="button" key={key} className="rounded-full border px-2 py-0.5" onClick={() => patchParams({ site_id: key })}>
                        {key} ({value})
                      </button>
                    ))}
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium uppercase text-muted-foreground">Project scope</label>
                <Input placeholder="project_id" value={projectId} onChange={(event) => patchParams({ project_id: event.target.value || undefined })} />
                <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
                  {Object.entries(facets.project_counts ?? {})
                    .slice(0, 5)
                    .map(([key, value]) => (
                      <button type="button" key={key} className="rounded-full border px-2 py-0.5" onClick={() => patchParams({ project_id: key })}>
                        {key} ({value})
                      </button>
                    ))}
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium uppercase text-muted-foreground">Risk level</label>
                <Input placeholder="risk_level" value={riskLevel} onChange={(event) => patchParams({ risk_level: event.target.value || undefined })} />
                <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
                  {Object.entries(facets.risk_level_counts ?? {})
                    .slice(0, 5)
                    .map(([key, value]) => (
                      <button type="button" key={key} className="rounded-full border px-2 py-0.5" onClick={() => patchParams({ risk_level: key })}>
                        {key} ({value})
                      </button>
                    ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-2">
            {loading ? <LoadingScreen label="Загрузка результатов поиска" /> : null}
            {!loading ? <ErrorState error={error ?? undefined} onRetry={() => setReloadNonce((prev) => prev + 1)} /> : null}
            {!loading && !error && q.trim().length > 0 && items.length === 0 ? <EmptyState title="Ничего не найдено" description="Попробуйте изменить запрос или фильтры." /> : null}
            {!loading && !error
              ? items.map((item) => (
                  <div key={`${item.entity_type}-${item.entity_id}`} className="rounded border p-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-sm text-muted-foreground">{item.entity_type}</div>
                        {item.deeplink && isExternalLink(item.deeplink) ? (
                          <a className="font-medium text-primary underline" href={item.deeplink} target="_blank" rel="noreferrer">
                            {item.title}
                          </a>
                        ) : (
                          <Link className="font-medium text-primary underline" to={item.deeplink ?? "#"}>
                            {item.title}
                          </Link>
                        )}
                      </div>
                      {item.status ? <div className="rounded-full border px-2 py-1 text-xs">{item.status}</div> : null}
                    </div>
                    {item.tags ? (
                      <div className="mt-1 text-xs text-muted-foreground">{Object.entries(item.tags).slice(0, 4).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}</div>
                    ) : null}
                    {item.snippet ? <div className="mt-2 text-sm text-muted-foreground">{item.snippet}</div> : null}
                  </div>
                ))
              : null}
          </div>
          {nextCursor ? (
            <Button onClick={() => void loadMore()} variant="outline" disabled={loadingMore}>
              {loadingMore ? "Загрузка..." : "Загрузить ещё"}
            </Button>
          ) : null}
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Недавние запросы</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {recent.map((item) => (
                <button key={item.id} type="button" className="flex w-full items-start gap-2 rounded border p-3 text-left hover:bg-muted" onClick={() => applySavedSearch(item)}>
                  <Clock3 className="mt-0.5 h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="font-medium">{item.q}</div>
                    <div className="text-xs text-muted-foreground">{item.types.join(", ") || "all types"}</div>
                  </div>
                </button>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Сохранённые поиски</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {saved.map((item) => (
                <div key={item.id} className="rounded border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <button type="button" className="text-left" onClick={() => applySavedSearch(item)}>
                      <div className="font-medium">{item.name}</div>
                      <div className="text-xs text-muted-foreground">{item.q}</div>
                      {Object.keys(item.filters ?? {}).length ? (
                        <div className="mt-1 text-xs text-muted-foreground">filters: {Object.entries(item.filters ?? {}).map(([key, value]) => `${key}=${String(value)}`).join(", ")}</div>
                      ) : null}
                    </button>
                    <Button variant="ghost" size="icon" onClick={() => void deleteSavedSearch(item.id).then(loadMemory)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default SearchPage;
