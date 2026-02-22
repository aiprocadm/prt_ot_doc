import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Input } from "@/components/ui/input";
import { searchGlobal, type SearchItem } from "@/api/search";
import { useDebounce } from "@/hooks/useDebounce";

export const GlobalSearch = () => {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SearchItem[]>([]);
  const debounced = useDebounce(query, 300);
  const navigate = useNavigate();

  useEffect(() => {
    if (!debounced.trim()) {
      setItems([]);
      return;
    }
    searchGlobal(debounced)
      .then((result) => setItems(result.items.slice(0, 8)))
      .catch(() => setItems([]));
  }, [debounced]);

  return (
    <div className="relative w-full max-w-xl">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input value={query} onChange={(e) => setQuery(e.target.value)} className="pl-9" placeholder="Глобальный поиск" />
      {items.length > 0 ? (
        <div className="absolute top-11 z-50 w-full rounded-md border bg-background p-2 shadow">
          {items.map((item) => (
            <button
              type="button"
              key={`${item.type}-${item.id}`}
              className="block w-full rounded px-2 py-1 text-left text-sm hover:bg-muted"
              onClick={() => navigate(item.type === "file" ? "/files" : "/documents")}
            >
              <div className="font-medium">{item.title}</div>
              {item.snippet ? <div className="text-xs text-muted-foreground">{item.snippet}</div> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
};
