import { BookmarkPlus, Clock3, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { createSavedSearch, deleteSavedSearch, fetchRecentSearches, fetchSavedSearches, fetchSearch, type SavedSearchItem, type SearchItem, type SearchType } from "@/api/search";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const tabs: Array<SearchType | "tasks" | "npa" | "contracts" | "orders"> = ["documents", "files", "people", "sites", "incidents", "inspections", "risk", "ppe", "training", "jobs", "templates", "tasks", "npa", "contracts", "orders"];

const SearchPage = () => {
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState<SearchItem[]>([]);
  const [facets, setFacets] = useState<Record<string, number>>({});
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [recent, setRecent] = useState<Array<{ id: string; q: string; types: string[] }>>([]);
  const [saved, setSaved] = useState<SavedSearchItem[]>([]);
  const q = params.get("q") ?? "";
  const type = (params.get("type") as SearchType | "tasks" | "npa" | "contracts" | "orders" | null) ?? "documents";

  const loadMemory = async () => {
    const [recentItems, savedItems] = await Promise.all([fetchRecentSearches(), fetchSavedSearches()]);
    setRecent(recentItems);
    setSaved(savedItems);
  };

  const setQuery = (value: string) => {
    const next = new URLSearchParams(params);
    next.set("q", value);
    setParams(next);
  };

  const activeTypes = useMemo(() => (type ? [type] : tabs) as SearchType[], [type]);

  useEffect(() => {
    void loadMemory().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!q.trim()) {
      setItems([]);
      setFacets({});
      return;
    }
    fetchSearch({ q, types: activeTypes })
      .then((data) => {
        setItems(data.items);
        setFacets(data.facets.type_counts ?? {});
        setNextCursor(data.next_cursor ?? null);
        void loadMemory();
      })
      .catch(() => {
        setItems([]);
        setFacets({});
      });
  }, [q, activeTypes]);

  const loadMore = async () => {
    if (!nextCursor) return;
    const data = await fetchSearch({ q, types: activeTypes, cursor: nextCursor });
    setItems((prev) => [...prev, ...data.items]);
    setNextCursor(data.next_cursor ?? null);
  };

  const saveCurrentSearch = async () => {
    if (!q.trim()) return;
    await createSavedSearch({ name: `${q.trim()} · ${type}`, q: q.trim(), types: activeTypes, filters: {} });
    await loadMemory();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Search Center</h1>
      <div className="grid gap-4 xl:grid-cols-[1.4fr,0.8fr]">
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-4 py-6">
              <Input value={q} placeholder="Поиск по системе" onChange={(e) => setQuery(e.target.value)} />
              <div className="flex flex-wrap gap-2">
                {tabs.map((tab) => (
                  <Button
                    key={tab}
                    variant={tab === type ? "default" : "outline"}
                    size="sm"
                    onClick={() => {
                      const next = new URLSearchParams(params);
                      next.set("type", tab);
                      setParams(next);
                    }}
                  >
                    {tab} ({facets[tab] ?? 0})
                  </Button>
                ))}
                <Button variant="outline" size="sm" onClick={() => void saveCurrentSearch()}>
                  <BookmarkPlus className="mr-2 h-4 w-4" /> Сохранить поиск
                </Button>
              </div>
            </CardContent>
          </Card>
          <div className="space-y-2">
            {items.map((item) => (
              <div key={`${item.entity_type}-${item.entity_id}`} className="rounded border p-3">
                <div className="text-sm text-muted-foreground">{item.entity_type}</div>
                <a className="font-medium text-primary underline" href={item.deeplink ?? "#"}>{item.title}</a>
                {item.status ? <div className="text-sm">Статус: {item.status}</div> : null}
                {item.tags ? <div className="mt-1 text-xs text-muted-foreground">{Object.entries(item.tags).slice(0, 3).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}</div> : null}
                {item.snippet ? <div className="text-sm text-muted-foreground">{item.snippet}</div> : null}
              </div>
            ))}
          </div>
          {nextCursor ? <Button onClick={loadMore} variant="outline">Загрузить ещё</Button> : null}
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Недавние запросы</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {recent.map((item) => (
                <button key={item.id} type="button" className="flex w-full items-start gap-2 rounded border p-3 text-left hover:bg-muted" onClick={() => setParams(new URLSearchParams({ q: item.q, type: item.types[0] ?? type }))}>
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
            <CardHeader><CardTitle>Сохранённые поиски</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {saved.map((item) => (
                <div key={item.id} className="rounded border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <button type="button" className="text-left" onClick={() => setParams(new URLSearchParams({ q: item.q, type: item.types[0] ?? type }))}>
                      <div className="font-medium">{item.name}</div>
                      <div className="text-xs text-muted-foreground">{item.q}</div>
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
