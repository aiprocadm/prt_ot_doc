import { useEffect, useState } from "react";

import {
  createSavedSearch,
  deleteSavedSearch,
  fetchRecentSearches,
  fetchSavedSearches,
  type SavedSearchItem,
} from "@/api/search";
import { useDebounce } from "@/hooks/useDebounce";
import { SearchFiltersPanel } from "@/pages/search/components/SearchFiltersPanel";
import { SearchQueryPanel } from "@/pages/search/components/SearchQueryPanel";
import { SearchResultsList } from "@/pages/search/components/SearchResultsList";
import { SearchSidebar } from "@/pages/search/components/SearchSidebar";
import { useSearchResults } from "@/pages/search/useSearchResults";
import { useSearchUrlState } from "@/pages/search/useSearchUrlState";

const SearchPage = () => {
  const { q, type, status, companyId, siteId, projectId, riskLevel, activeTypes, activeFilterCount, patchParams, replaceWithSavedSearch, tabs } = useSearchUrlState();
  const [recent, setRecent] = useState<Array<{ id: string; q: string; types: string[] }>>([]);
  const [saved, setSaved] = useState<SavedSearchItem[]>([]);
  const debouncedQ = useDebounce(q, 350);

  const loadMemory = async () => {
    const [recentItems, savedItems] = await Promise.all([fetchRecentSearches(), fetchSavedSearches()]);
    setRecent(recentItems);
    setSaved(savedItems);
  };

  const { items, facets, nextCursor, loading, loadingMore, error, loadMore, reload } = useSearchResults({
    query: debouncedQ,
    activeTypes,
    status,
    companyId,
    siteId,
    projectId,
    riskLevel,
    onSearchSuccess: () => {
      void loadMemory().catch(() => undefined);
    },
  });

  useEffect(() => {
    void loadMemory().catch(() => undefined);
  }, []);

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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Search Center</h1>
        <div className="rounded-full border px-3 py-1 text-xs text-muted-foreground">Активных фильтров: {activeFilterCount}</div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.4fr,0.8fr]">
        <div className="space-y-4">
          <SearchQueryPanel
            query={q}
            type={type}
            tabs={tabs}
            facets={facets}
            onQueryChange={(value) => patchParams({ q: value })}
            onTypeChange={(value) => patchParams({ type: value })}
            onSaveSearch={saveCurrentSearch}
          />
          <SearchFiltersPanel
            facets={facets}
            status={status}
            companyId={companyId}
            siteId={siteId}
            projectId={projectId}
            riskLevel={riskLevel}
            onPatch={patchParams}
          />
          <SearchResultsList
            query={q}
            items={items}
            loading={loading}
            loadingMore={loadingMore}
            error={error}
            canLoadMore={Boolean(nextCursor)}
            onRetry={reload}
            onLoadMore={loadMore}
          />
        </div>
        <SearchSidebar
          recent={recent}
          saved={saved}
          onApplySavedSearch={replaceWithSavedSearch}
          onDeleteSavedSearch={async (id) => {
            await deleteSavedSearch(id);
            await loadMemory();
          }}
        />
      </div>
    </div>
  );
};

export default SearchPage;
