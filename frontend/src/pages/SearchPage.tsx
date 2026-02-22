import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchSearch, type SearchItem, type SearchType } from "@/api/search";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const tabs: SearchType[] = ["documents", "files", "people", "sites", "incidents", "inspections"];

const SearchPage = () => {
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState<SearchItem[]>([]);
  const [facets, setFacets] = useState<Record<string, number>>({});
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const q = params.get("q") ?? "";
  const type = (params.get("type") as SearchType | null) ?? "documents";

  const setQuery = (value: string) => {
    const next = new URLSearchParams(params);
    next.set("q", value);
    setParams(next);
  };

  const activeTypes = useMemo(() => (type ? [type] : tabs), [type]);

  useEffect(() => {
    if (!q.trim()) {
      setItems([]);
      setFacets({});
      return;
    }
    fetchSearch({ q, types: activeTypes })
      .then((data) => {
        setItems(data.items);
        setFacets(data.facets);
        setNextCursor(data.next_cursor ?? null);
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

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Глобальный поиск</h1>
      <Input value={q} placeholder="Поиск по системе" onChange={(e) => setQuery(e.target.value)} />
      <div className="flex gap-2 flex-wrap">
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
      </div>
      <div className="space-y-2">
        {items.map((item) => (
          <div key={`${item.entity_type}-${item.entity_id}`} className="rounded border p-3">
            <div className="text-sm text-muted-foreground">{item.entity_type}</div>
            <div className="font-medium">{item.title}</div>
            {item.status ? <div className="text-sm">Статус: {item.status}</div> : null}
            {item.snippet ? <div className="text-sm text-muted-foreground" dangerouslySetInnerHTML={{ __html: item.snippet }} /> : null}
          </div>
        ))}
      </div>
      {nextCursor ? (
        <Button onClick={loadMore} variant="outline">
          Загрузить ещё
        </Button>
      ) : null}
    </div>
  );
};

export default SearchPage;
