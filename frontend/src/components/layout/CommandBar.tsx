import { Command, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useNavMenuData } from "@/hooks/useNavMenuData";
import { flattenNavGroups, matchesNavCommandQuery } from "@/router/navVisibility";

export const CommandBar = () => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const { visibleGroups } = useNavMenuData();

  const flatItems = useMemo(() => flattenNavGroups(visibleGroups), [visibleGroups]);

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
    const byGroup = new Map<string, typeof filtered>();
    for (const item of filtered) {
      const list = byGroup.get(item.groupTitle) ?? [];
      list.push(item);
      byGroup.set(item.groupTitle, list);
    }
    return Array.from(byGroup.entries()).map(([title, items]) => ({ title, items }));
  }, [filtered, query]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-md border px-2 py-2 text-xs text-muted-foreground hover:bg-muted sm:px-3 lg:py-2"
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
                      <Link
                        key={item.id}
                        to={item.path}
                        onClick={() => setOpen(false)}
                        className="block rounded px-2 py-2 text-sm hover:bg-muted"
                      >
                        <span className="font-medium">{item.label}</span>
                        {query.trim() ? (
                          <span className="mt-0.5 block text-xs text-muted-foreground">{item.groupTitle}</span>
                        ) : null}
                      </Link>
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
