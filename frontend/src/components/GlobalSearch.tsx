import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type Ref } from "react";
import { useNavigate } from "react-router-dom";

import { fetchRecentSearches, searchGlobal, type SearchItem } from "@/api/search";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/useDebounce";
import { useMediaQuery } from "@/hooks/useMediaQuery";

const toTabType = (entityType: string): string => {
  const mapping: Record<string, string> = {
    document: "documents",
    person: "people",
    site: "sites",
    incident: "incidents",
    inspection: "inspections",
    file: "files",
    prescription: "jobs",
    template: "templates"
  };
  return mapping[entityType] ?? "documents";
};

const INPUT_ID = "global-search-input";

type SearchPanelProps = {
  inputRef?: Ref<HTMLInputElement | null>;
  onNavigate?: () => void;
};

const GlobalSearchPanel = ({ inputRef, onNavigate }: SearchPanelProps) => {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<SearchItem[]>([]);
  const [recent, setRecent] = useState<Array<{ id: string; q: string; types: string[] }>>([]);
  const debounced = useDebounce(query, 300);
  const navigate = useNavigate();
  const internalRef = useRef<HTMLInputElement | null>(null);
  const mergedRef = (inputRef ?? internalRef) as Ref<HTMLInputElement>;

  useEffect(() => {
    void fetchRecentSearches()
      .then((result) => setRecent(Array.isArray(result) ? result : []))
      .catch(() => setRecent([]));
  }, []);

  useEffect(() => {
    if (!debounced.trim()) {
      setItems([]);
      return;
    }
    searchGlobal(debounced)
      .then((result) => setItems(Array.isArray(result.items) ? result.items.slice(0, 10) : []))
      .catch(() => setItems([]));
  }, [debounced]);

  const grouped = useMemo(
    () =>
      items.reduce<Record<string, SearchItem[]>>((acc, item) => {
        const key = item.entity_type;
        acc[key] = acc[key] ?? [];
        acc[key].push(item);
        return acc;
      }, {}),
    [items]
  );

  const go = (path: string) => {
    navigate(path);
    onNavigate?.();
  };

  return (
    <div className="relative w-full max-w-xl">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        ref={mergedRef}
        id={INPUT_ID}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && query.trim()) {
            go(`/search?q=${encodeURIComponent(query.trim())}`);
          }
        }}
        className="pl-9"
        placeholder="Глобальный поиск (/): документы, сотрудники, инциденты, НПА, задачи"
      />
      {items.length > 0 || (!query.trim() && recent.length > 0) ? (
        <div className="absolute top-11 z-50 w-full rounded-md border bg-background p-2 shadow">
          {query.trim() ? (
            Object.entries(grouped).map(([group, groupItems]) => (
              <div key={group} className="mb-2 last:mb-0">
                <div className="px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">{group}</div>
                {groupItems.map((item) => (
                  <button
                    type="button"
                    key={`${item.entity_type}-${item.entity_id}`}
                    className="block w-full rounded px-2 py-1 text-left text-sm hover:bg-muted"
                    onClick={() =>
                      go(item.deeplink ?? `/search?q=${encodeURIComponent(query)}&type=${toTabType(item.entity_type)}`)
                    }
                  >
                    <div className="font-medium">{item.title}</div>
                    {item.snippet ? <div className="text-xs text-muted-foreground">{item.snippet}</div> : null}
                  </button>
                ))}
              </div>
            ))
          ) : (
            <div className="space-y-2">
              <div className="px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">Недавние запросы</div>
              {recent.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className="block w-full rounded px-2 py-1 text-left text-sm hover:bg-muted"
                  onClick={() =>
                    go(`/search?q=${encodeURIComponent(item.q)}${item.types[0] ? `&type=${encodeURIComponent(item.types[0])}` : ""}`)
                  }
                >
                  <div className="font-medium">{item.q}</div>
                  <div className="text-xs text-muted-foreground">{item.types.join(", ") || "все типы"}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
};

export const GlobalSearch = () => {
  const isLg = useMediaQuery("(min-width: 1024px)");
  const [mobileOpen, setMobileOpen] = useState(false);
  const mobileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "/" && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement)) {
        event.preventDefault();
        if (isLg) {
          const input = document.getElementById(INPUT_ID) as HTMLInputElement | null;
          input?.focus();
        } else {
          setMobileOpen(true);
          window.setTimeout(() => mobileInputRef.current?.focus(), 0);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isLg]);

  useEffect(() => {
    if (mobileOpen) {
      window.setTimeout(() => mobileInputRef.current?.focus(), 0);
    }
  }, [mobileOpen]);

  if (isLg) {
    return (
      <div className="flex w-full min-w-0 max-w-xl justify-center">
        <GlobalSearchPanel />
      </div>
    );
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="h-11 w-11 shrink-0 lg:hidden"
        aria-label="Открыть глобальный поиск"
        onClick={() => setMobileOpen(true)}
      >
        <Search className="h-4 w-4" />
      </Button>
      <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
        <DialogContent className="max-w-lg overflow-visible">
          <DialogHeader>
            <DialogTitle>Поиск</DialogTitle>
          </DialogHeader>
          <GlobalSearchPanel inputRef={mobileInputRef} onNavigate={() => setMobileOpen(false)} />
        </DialogContent>
      </Dialog>
    </>
  );
};
