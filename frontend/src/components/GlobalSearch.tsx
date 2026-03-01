import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { searchGlobal, type SearchItem } from "@/api/search";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/useDebounce";

const toTabType = (entityType: string): string => {
  const mapping: Record<string, string> = {
    Document: "documents",
    Person: "people",
    Site: "sites",
    Incident: "incidents",
    Inspection: "inspections",
    File: "files",
  };
  return mapping[entityType] ?? "documents";
};

export const GlobalSearch = () => {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SearchItem[]>([]);
  const debounced = useDebounce(query, 300);
  const navigate = useNavigate();

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "/" && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement)) {
        event.preventDefault();
        const input = document.getElementById("global-search-input") as HTMLInputElement | null;
        input?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!debounced.trim()) {
      setItems([]);
      return;
    }
    searchGlobal(debounced)
      .then((result) => setItems(result.items.slice(0, 10)))
      .catch(() => setItems([]));
  }, [debounced]);

  const grouped = useMemo(() => {
    return items.reduce<Record<string, SearchItem[]>>((acc, item) => {
      const key = item.entity_type;
      acc[key] = acc[key] ?? [];
      acc[key].push(item);
      return acc;
    }, {});
  }, [items]);

  return (
    <div className="relative w-full max-w-xl">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        id="global-search-input"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && query.trim()) {
            navigate(`/search?q=${encodeURIComponent(query.trim())}`);
          }
        }}
        className="pl-9"
        placeholder="Глобальный поиск (/)"
      />
      {items.length > 0 ? (
        <div className="absolute top-11 z-50 w-full rounded-md border bg-background p-2 shadow">
          {Object.entries(grouped).map(([group, groupItems]) => (
            <div key={group} className="mb-2 last:mb-0">
              <div className="px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">{group}</div>
              {groupItems.map((item) => (
                <button
                  type="button"
                  key={`${item.entity_type}-${item.entity_id}`}
                  className="block w-full rounded px-2 py-1 text-left text-sm hover:bg-muted"
                  onClick={() => navigate(item.deeplink ?? `/search?q=${encodeURIComponent(query)}&type=${toTabType(item.entity_type)}`)}
                >
                  <div className="font-medium">{item.title}</div>
                  {item.snippet ? <div className="text-xs text-muted-foreground">{item.snippet}</div> : null}
                </button>
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
};
