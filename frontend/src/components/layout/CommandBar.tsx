import { Command, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { localStorageGetItem, localStorageSetItem } from "@/utils/browserStorage";
import { trackUxMetric } from "@/utils/uxMetrics";
import { useNavMenuData } from "@/hooks/useNavMenuData";
import { flattenNavGroups, matchesNavCommandQuery } from "@/router/navVisibility";

const FAVORITE_PATHS_STORAGE_KEY = "ux.commandbar.favoritePaths.v1";
const RECENT_PATHS_STORAGE_KEY = "ux.commandbar.recentPaths.v1";
const MAX_RECENT = 8;

const readPaths = (key: string): string[] => {
  const raw = localStorageGetItem(key);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as string[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

export const CommandBar = () => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [favoritePaths, setFavoritePaths] = useState<string[]>([]);
  const [recentPaths, setRecentPaths] = useState<string[]>([]);
  const { visibleGroups } = useNavMenuData();

  const flatItems = useMemo(() => flattenNavGroups(visibleGroups), [visibleGroups]);

  useEffect(() => {
    setFavoritePaths(readPaths(FAVORITE_PATHS_STORAGE_KEY));
    setRecentPaths(readPaths(RECENT_PATHS_STORAGE_KEY));
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return flatItems;
    return flatItems.filter((item) => matchesNavCommandQuery(item, q));
  }, [flatItems, query]);

  const groupedForDisplay = useMemo(() => {
    const q = query.trim();
    if (q) {
      return [{ title: "Результаты", items: filtered }];
    }

    const favorites = filtered.filter((item) => favoritePaths.includes(item.path));
    const recent = recentPaths
      .map((path) => filtered.find((item) => item.path === path))
      .filter((item): item is (typeof filtered)[number] => Boolean(item));

    const byGroup = new Map<string, typeof filtered>();
    for (const item of filtered) {
      const list = byGroup.get(item.groupTitle) ?? [];
      list.push(item);
      byGroup.set(item.groupTitle, list);
    }
    const grouped = Array.from(byGroup.entries()).map(([title, items]) => ({ title, items }));
    return [
      ...(favorites.length ? [{ title: "Избранное", items: favorites }] : []),
      ...(recent.length ? [{ title: "Недавние", items: recent }] : []),
      ...grouped
    ];
  }, [favoritePaths, filtered, query, recentPaths]);

  const toggleFavorite = (path: string) => {
    setFavoritePaths((prev) => {
      const next = prev.includes(path) ? prev.filter((item) => item !== path) : [path, ...prev].slice(0, 20);
      localStorageSetItem(FAVORITE_PATHS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const rememberRecent = (path: string) => {
    setRecentPaths((prev) => {
      const next = [path, ...prev.filter((item) => item !== path)].slice(0, MAX_RECENT);
      localStorageSetItem(RECENT_PATHS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex min-h-11 items-center gap-2 rounded-md border px-2 py-2 text-xs text-muted-foreground hover:bg-muted sm:px-3 lg:py-2"
        aria-label="Открыть палитру команд"
      >
        <Command className="h-3.5 w-3.5 shrink-0" />
        <span className="hidden sm:inline">Команды</span>
        <span className="hidden rounded border px-1.5 py-0.5 text-[10px] lg:inline">Ctrl+K</span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Палитра команд</DialogTitle>
            <DialogDescription>Поиск разделов и быстрый переход по платформе</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Найти раздел по названию или группе"
                className="pl-9"
              />
            </div>
            <div className="max-h-80 space-y-4 overflow-y-auto rounded-md border p-2">
              {groupedForDisplay.map((section) => (
                <div key={section.title}>
                  <div className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{section.title}</div>
                  <div className="space-y-1">
                    {section.items.map((item) => (
                      <div key={item.id} className="flex items-start justify-between rounded px-2 py-2 text-sm hover:bg-muted">
                        <Link
                          to={item.path}
                          onClick={() => {
                            rememberRecent(item.path);
                            trackUxMetric("navigation_click", { source: "commandbar", path: item.path });
                            trackUxMetric("time_to_first_action", { source: "commandbar" });
                            setOpen(false);
                          }}
                          className="min-w-0 flex-1"
                        >
                          <span className="font-medium">{item.label}</span>
                          {query.trim() ? (
                            <span className="mt-0.5 block text-xs text-muted-foreground">{item.groupTitle}</span>
                          ) : null}
                        </Link>
                        <button
                          type="button"
                          className="ml-2 rounded px-1 text-xs text-muted-foreground hover:text-foreground"
                          aria-label={favoritePaths.includes(item.path) ? "Убрать из избранного" : "Добавить в избранное"}
                          onClick={() => toggleFavorite(item.path)}
                        >
                          {favoritePaths.includes(item.path) ? "★" : "☆"}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {!filtered.length && <p className="px-2 py-3 text-sm text-muted-foreground">Ничего не найдено</p>}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};
