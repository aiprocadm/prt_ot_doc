import { Command, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  fetchSavedSearches,
  searchGlobal,
  type SavedSearchItem,
  type SearchItem,
} from "@/api/search";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/useDebounce";
import { useNavMenuData } from "@/hooks/useNavMenuData";
import {
  flattenNavGroups,
  matchesNavCommandQuery,
} from "@/router/navVisibility";
import {
  localStorageGetItem,
  localStorageSetItem,
} from "@/utils/browserStorage";
import { trackUxMetric } from "@/utils/uxMetrics";

const FAVORITE_PATHS_STORAGE_KEY = "ux.commandbar.favoritePaths.v1";
const RECENT_PATHS_STORAGE_KEY = "ux.commandbar.recentPaths.v1";
const RECENT_ENTITIES_STORAGE_KEY = "ux.commandbar.recentEntities.v1";
const MAX_RECENT = 8;
const MAX_ENTITY_RESULTS = 8;
const MAX_SAVED_SEARCHES = 6;
const MAX_RECENT_ENTITIES = 8;
// 30 days. Older items get pruned on load — keeps the section relevant to
// the user's current work and prevents the storage payload from growing
// unbounded over a long-lived session.
const RECENT_ENTITY_TTL_MS = 30 * 24 * 60 * 60 * 1000;

interface RecentEntityRecord {
  entity_type: string;
  entity_id: string;
  title: string;
  path: string;
  opened_at: number; // Unix ms
}

// Saved searches reuse the same URL contract as the dedicated search page
// (`useSearchUrlState`): `?q=<q>&type=<types[0]>&status=...&company_id=...&site_id=...`.
// Apply a saved search by navigating with these params; the /search page
// will hydrate from URL and re-run its query with the saved filter state.
const buildSavedSearchPath = (item: SavedSearchItem): string => {
  const params = new URLSearchParams();
  if (item.q) params.set("q", item.q);
  const firstType = Array.isArray(item.types) ? item.types[0] : undefined;
  if (firstType) params.set("type", firstType);
  const filters = (item.filters ?? {}) as Record<string, unknown>;
  if (typeof filters.status === "string" && filters.status)
    params.set("status", filters.status);
  if (typeof filters.company_id === "string" && filters.company_id)
    params.set("company_id", filters.company_id);
  if (typeof filters.site_id === "string" && filters.site_id)
    params.set("site_id", filters.site_id);
  if (typeof filters.project_id === "string" && filters.project_id)
    params.set("project_id", filters.project_id);
  if (typeof filters.risk_level === "string" && filters.risk_level)
    params.set("risk_level", filters.risk_level);
  const qs = params.toString();
  return qs ? `/search?${qs}` : "/search";
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  person: "Сотрудники",
  people: "Сотрудники",
  document: "Документы",
  documents: "Документы",
  file: "Файлы",
  files: "Файлы",
  site: "Объекты",
  sites: "Объекты",
  company: "Компании",
  contractor: "Подрядчики",
  template: "Шаблоны",
  templates: "Шаблоны",
  package: "Пакеты",
  packages: "Пакеты",
  risk: "Риски",
  risk_map: "Карты рисков",
  ppe_issue: "СИЗ",
  training_enrollment: "Обучение",
  briefing_entry: "Инструктажи",
  incident: "Инциденты",
  incidents: "Инциденты",
  inspection: "Проверки",
  inspections: "Проверки",
  prescription: "Предписания",
  task: "Задачи",
  tasks: "Задачи",
  workflow_task: "Задачи процесса",
  npa: "НПА",
  contract: "Договоры",
  order: "Заказы",
};

interface ExecutableCommand {
  id: string;
  label: string;
  description: string;
  triggers: string[];
  path: string;
}

const EXECUTABLE_COMMANDS: ExecutableCommand[] = [
  {
    id: "create-document",
    label: "Создать документ",
    description: "Открыть мастер создания документа",
    triggers: [
      "создать документ",
      "новый документ",
      "create document",
      "new document",
    ],
    path: "/documents?action=create",
  },
  {
    id: "create-incident",
    label: "Зарегистрировать инцидент",
    description: "Открыть форму регистрации происшествия",
    triggers: [
      "создать инцидент",
      "новый инцидент",
      "create incident",
      "new incident",
      "происшествие",
    ],
    path: "/incidents?action=create",
  },
  {
    id: "create-inspection",
    label: "Запланировать проверку",
    description: "Открыть форму планирования проверки",
    triggers: [
      "создать проверку",
      "новая проверка",
      "запланировать проверку",
      "create inspection",
      "new inspection",
    ],
    path: "/inspections?action=create",
  },
  {
    id: "assign-training",
    label: "Назначить обучение",
    description: "Открыть мастер назначения обучения",
    triggers: [
      "назначить обучение",
      "обучить",
      "assign training",
      "new training",
    ],
    path: "/training?action=create",
  },
  {
    id: "issue-ppe",
    label: "Выдать СИЗ",
    description: "Открыть форму выдачи СИЗ",
    triggers: ["выдать сиз", "выдача сиз", "новая выдача сиз", "issue ppe"],
    path: "/ppe?action=create",
  },
  {
    id: "open-calendar",
    label: "Открыть календарь",
    description: "Перейти в Умный календарь",
    triggers: ["календарь", "calendar", "smart calendar"],
    path: "/calendar",
  },
  {
    id: "open-search",
    label: "Расширенный поиск",
    description: "Открыть страницу глобального поиска",
    triggers: ["поиск", "глобальный поиск", "search"],
    path: "/search",
  },
];

const matchesCommand = (command: ExecutableCommand, query: string): boolean => {
  const lower = query.toLowerCase();
  if (command.label.toLowerCase().includes(lower)) return true;
  return command.triggers.some(
    (trigger) => trigger.includes(lower) || lower.includes(trigger),
  );
};

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

// Recent entities are stored client-side: there is no `/search/recent-entities`
// backend endpoint, and the privacy posture is "what I clicked from MY
// palette" rather than "what my org clicked." Storage shape is the bare
// minimum needed to render the row + navigate: entity_type + entity_id +
// title + path + opened_at. Old entries (> TTL) are pruned on load so the
// section stays relevant without growing unbounded.
const readRecentEntities = (now: number = Date.now()): RecentEntityRecord[] => {
  const raw = localStorageGetItem(RECENT_ENTITIES_STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as RecentEntityRecord[];
    if (!Array.isArray(parsed)) return [];
    // Validate shape, then prune by TTL.
    return parsed
      .filter(
        (item): item is RecentEntityRecord =>
          typeof item === "object" &&
          item !== null &&
          typeof item.entity_type === "string" &&
          typeof item.entity_id === "string" &&
          typeof item.title === "string" &&
          typeof item.path === "string" &&
          typeof item.opened_at === "number",
      )
      .filter((item) => now - item.opened_at <= RECENT_ENTITY_TTL_MS)
      .slice(0, MAX_RECENT_ENTITIES);
  } catch {
    return [];
  }
};

const writeRecentEntities = (items: RecentEntityRecord[]): void => {
  try {
    localStorageSetItem(RECENT_ENTITIES_STORAGE_KEY, JSON.stringify(items));
  } catch {
    // Quota exceeded / disabled storage — silently degrade, recent-entities
    // section just won't update. Not worth surfacing to the user.
  }
};

export const CommandBar = () => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [favoritePaths, setFavoritePaths] = useState<string[]>([]);
  const [recentPaths, setRecentPaths] = useState<string[]>([]);
  const [entityResults, setEntityResults] = useState<SearchItem[]>([]);
  const [entitySearchLoading, setEntitySearchLoading] = useState(false);
  const [savedSearches, setSavedSearches] = useState<SavedSearchItem[]>([]);
  const [savedSearchesLoaded, setSavedSearchesLoaded] = useState(false);
  const [recentEntities, setRecentEntities] = useState<RecentEntityRecord[]>(
    [],
  );
  const [selectedIndex, setSelectedIndex] = useState(0);
  const itemRefs = useRef<Array<HTMLAnchorElement | null>>([]);
  const debouncedQuery = useDebounce(query, 300);
  const navigate = useNavigate();
  const { visibleGroups } = useNavMenuData();

  const flatItems = useMemo(
    () => flattenNavGroups(visibleGroups),
    [visibleGroups],
  );

  useEffect(() => {
    setFavoritePaths(readPaths(FAVORITE_PATHS_STORAGE_KEY));
    setRecentPaths(readPaths(RECENT_PATHS_STORAGE_KEY));
    setRecentEntities(readRecentEntities());
  }, []);

  // Lazy-load saved searches on the first palette open. Saved searches change
  // rarely (manual create/delete on /search page), so we keep them in memory
  // for the rest of the session rather than refetching on every Ctrl+K.
  // Unauthenticated/error responses degrade silently — saved-search section
  // just renders empty and the rest of the palette is unaffected.
  useEffect(() => {
    if (!open || savedSearchesLoaded) return;
    let active = true;
    fetchSavedSearches()
      .then((items) => {
        if (!active) return;
        setSavedSearches(Array.isArray(items) ? items : []);
      })
      .catch(() => {
        if (!active) return;
        setSavedSearches([]);
      })
      .finally(() => {
        if (active) setSavedSearchesLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [open, savedSearchesLoaded]);

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

  // Entity search: fire only when palette is open and query is non-empty.
  // AbortController cancels in-flight request when the user keeps typing or
  // closes the palette — avoids race conditions where a slow response
  // overwrites a newer one.
  useEffect(() => {
    if (!open) {
      setEntityResults([]);
      setEntitySearchLoading(false);
      return;
    }
    const trimmed = debouncedQuery.trim();
    if (!trimmed) {
      setEntityResults([]);
      setEntitySearchLoading(false);
      return;
    }
    const controller = new AbortController();
    setEntitySearchLoading(true);
    searchGlobal(trimmed)
      .then((result) => {
        if (controller.signal.aborted) return;
        const items = Array.isArray(result?.items)
          ? result.items.slice(0, MAX_ENTITY_RESULTS)
          : [];
        setEntityResults(items);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setEntityResults([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) setEntitySearchLoading(false);
      });
    return () => controller.abort();
  }, [debouncedQuery, open]);

  const matchedCommands = useMemo(() => {
    const trimmed = query.trim();
    if (!trimmed) return [];
    return EXECUTABLE_COMMANDS.filter((command) =>
      matchesCommand(command, trimmed),
    ).slice(0, 4);
  }, [query]);

  // Saved searches are a discovery affordance: they're shown only when the
  // query is empty (palette is in "browse" mode). When the user starts
  // typing, the focus shifts to live results and actions — saved searches
  // would just compete for attention.
  const visibleSavedSearches = useMemo(() => {
    if (query.trim()) return [];
    return savedSearches.slice(0, MAX_SAVED_SEARCHES);
  }, [query, savedSearches]);

  // Recently opened entities follow the same discovery-only pattern: shown
  // when the palette is in browse mode (empty query), hidden once the user
  // starts typing. Ordered newest-first since `rememberRecentEntity` always
  // hoists the clicked item to position 0.
  const visibleRecentEntities = useMemo(() => {
    if (query.trim()) return [];
    return recentEntities.slice(0, MAX_RECENT_ENTITIES);
  }, [query, recentEntities]);

  const entityGroups = useMemo(() => {
    if (entityResults.length === 0) return [];
    const groups = new Map<string, SearchItem[]>();
    entityResults.forEach((item) => {
      const list = groups.get(item.entity_type) ?? [];
      list.push(item);
      groups.set(item.entity_type, list);
    });
    return [...groups.entries()].map(([entityType, items]) => ({
      entityType,
      label: ENTITY_TYPE_LABELS[entityType] ?? entityType,
      items,
    }));
  }, [entityResults]);

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

    const favorites = filtered.filter((item) =>
      favoritePaths.includes(item.path),
    );
    const recent = recentPaths
      .map((path) => filtered.find((item) => item.path === path))
      .filter((item): item is (typeof filtered)[number] => Boolean(item));

    const byGroup = new Map<string, typeof filtered>();
    for (const item of filtered) {
      const list = byGroup.get(item.groupTitle) ?? [];
      list.push(item);
      byGroup.set(item.groupTitle, list);
    }
    const grouped = Array.from(byGroup.entries()).map(([title, items]) => ({
      title,
      items,
    }));
    return [
      ...(favorites.length ? [{ title: "Избранное", items: favorites }] : []),
      ...(recent.length ? [{ title: "Недавние", items: recent }] : []),
      ...grouped,
    ];
  }, [favoritePaths, filtered, query, recentPaths]);

  const toggleFavorite = (path: string) => {
    setFavoritePaths((prev) => {
      const next = prev.includes(path)
        ? prev.filter((item) => item !== path)
        : [path, ...prev].slice(0, 20);
      localStorageSetItem(FAVORITE_PATHS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const rememberRecent = (path: string) => {
    setRecentPaths((prev) => {
      const next = [path, ...prev.filter((item) => item !== path)].slice(
        0,
        MAX_RECENT,
      );
      localStorageSetItem(RECENT_PATHS_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  // Hoists the entity to position 0 (newest-first), dedups against the same
  // entity_type+entity_id (re-clicking the same row should not produce
  // duplicates — instead it refreshes the title and timestamp), and caps at
  // MAX_RECENT_ENTITIES. Title is captured at click time so it reflects what
  // the user actually saw rather than what the entity is later renamed to.
  const rememberRecentEntity = (item: SearchItem, path: string) => {
    const record: RecentEntityRecord = {
      entity_type: item.entity_type,
      entity_id: item.entity_id,
      title: item.title,
      path,
      opened_at: Date.now(),
    };
    setRecentEntities((prev) => {
      const next = [
        record,
        ...prev.filter(
          (existing) =>
            !(
              existing.entity_type === record.entity_type &&
              existing.entity_id === record.entity_id
            ),
        ),
      ].slice(0, MAX_RECENT_ENTITIES);
      writeRecentEntities(next);
      return next;
    });
  };

  // Flat ordered list of all keyboard-navigable items in the same order
  // they appear on screen (actions → entities → nav). The arrow keys walk
  // this list; Enter triggers `activate()`. Keeping render and navigation
  // in sync via a single source-of-truth array means we cannot drift —
  // every screen item maps 1:1 to an index here.
  type NavigableItem = {
    key: string;
    path: string;
    kind: "action" | "entity" | "saved" | "recent-entity" | "nav";
    activate: () => void;
  };

  const navigableItems = useMemo<NavigableItem[]>(() => {
    const items: NavigableItem[] = [];
    matchedCommands.forEach((command) => {
      items.push({
        key: `action-${command.id}`,
        path: command.path,
        kind: "action",
        activate: () => {
          trackUxMetric("navigation_click", {
            source: "commandbar-action",
            path: command.path,
          });
          navigate(command.path);
          setOpen(false);
        },
      });
    });
    entityGroups.forEach((group) => {
      group.items.forEach((item) => {
        const path =
          item.deeplink ?? `/search?q=${encodeURIComponent(query.trim())}`;
        items.push({
          key: `entity-${item.entity_type}-${item.entity_id}`,
          path,
          kind: "entity",
          activate: () => {
            trackUxMetric("navigation_click", {
              source: "commandbar-entity",
              entity_type: item.entity_type,
            });
            rememberRecentEntity(item, path);
            navigate(path);
            setOpen(false);
          },
        });
      });
    });
    visibleSavedSearches.forEach((saved) => {
      const path = buildSavedSearchPath(saved);
      items.push({
        key: `saved-${saved.id}`,
        path,
        kind: "saved",
        activate: () => {
          trackUxMetric("navigation_click", {
            source: "commandbar-saved",
            path,
          });
          navigate(path);
          setOpen(false);
        },
      });
    });
    visibleRecentEntities.forEach((recent) => {
      items.push({
        key: `recent-entity-${recent.entity_type}-${recent.entity_id}`,
        path: recent.path,
        kind: "recent-entity",
        activate: () => {
          trackUxMetric("navigation_click", {
            source: "commandbar-recent-entity",
            entity_type: recent.entity_type,
          });
          // Re-hoist (refreshes opened_at so a re-opened entity stays at
          // position 0 and doesn't age out as quickly).
          rememberRecentEntity(
            {
              kind: "entity",
              entity_type: recent.entity_type,
              entity_id: recent.entity_id,
              title: recent.title,
            } as SearchItem,
            recent.path,
          );
          navigate(recent.path);
          setOpen(false);
        },
      });
    });
    groupedForDisplay.forEach((section) => {
      section.items.forEach((navItem) => {
        items.push({
          key: `nav-${navItem.id}`,
          path: navItem.path,
          kind: "nav",
          activate: () => {
            rememberRecent(navItem.path);
            trackUxMetric("navigation_click", {
              source: "commandbar",
              path: navItem.path,
            });
            trackUxMetric("time_to_first_action", { source: "commandbar" });
            navigate(navItem.path);
            setOpen(false);
          },
        });
      });
    });
    return items;
  }, [
    entityGroups,
    groupedForDisplay,
    matchedCommands,
    navigate,
    query,
    visibleRecentEntities,
    visibleSavedSearches,
  ]);

  const indexByKey = useMemo(() => {
    const map = new Map<string, number>();
    navigableItems.forEach((item, index) => map.set(item.key, index));
    return map;
  }, [navigableItems]);

  // Reset highlight when the visible list changes (new query, new results)
  // or when the palette opens. Without this the user could land on a
  // selectedIndex that has nothing to navigate to.
  useEffect(() => {
    setSelectedIndex(0);
  }, [navigableItems.length, open]);

  // Auto-scroll the selected row into view so arrow-key navigation
  // through a long list does not strand the highlight off-screen.
  useEffect(() => {
    const node = itemRefs.current[selectedIndex];
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIndex]);

  const handleInputKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (navigableItems.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % navigableItems.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedIndex(
        (prev) => (prev - 1 + navigableItems.length) % navigableItems.length,
      );
    } else if (event.key === "Enter") {
      const target = navigableItems[selectedIndex] ?? navigableItems[0];
      if (target) {
        event.preventDefault();
        target.activate();
      }
    } else if (event.key === "Home") {
      event.preventDefault();
      setSelectedIndex(0);
    } else if (event.key === "End") {
      event.preventDefault();
      setSelectedIndex(navigableItems.length - 1);
    }
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
        <span className="hidden rounded border px-1.5 py-0.5 text-[10px] lg:inline">
          Ctrl+K
        </span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Палитра команд</DialogTitle>
            <DialogDescription>
              Поиск разделов и быстрый переход по платформе
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleInputKeyDown}
                placeholder="Найти раздел по названию или группе"
                className="pl-9"
                aria-controls="commandbar-results"
                aria-activedescendant={
                  navigableItems[selectedIndex]
                    ? `commandbar-item-${navigableItems[selectedIndex].key}`
                    : undefined
                }
              />
            </div>
            <div
              className="max-h-96 space-y-4 overflow-y-auto rounded-md border p-2"
              id="commandbar-results"
              role="listbox"
              aria-label="Результаты палитры"
            >
              {matchedCommands.length > 0 ? (
                <div data-testid="commandbar-actions">
                  <div className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Действия
                  </div>
                  <div className="space-y-1">
                    {matchedCommands.map((command) => {
                      const navKey = `action-${command.id}`;
                      const index = indexByKey.get(navKey) ?? -1;
                      const selected = index === selectedIndex;
                      return (
                        <Link
                          key={command.id}
                          to={command.path}
                          ref={(node) => {
                            if (index >= 0) itemRefs.current[index] = node;
                          }}
                          id={`commandbar-item-${navKey}`}
                          role="option"
                          aria-selected={selected}
                          data-command-id={command.id}
                          data-selected={selected || undefined}
                          onClick={() => {
                            trackUxMetric("navigation_click", {
                              source: "commandbar-action",
                              path: command.path,
                            });
                            setOpen(false);
                          }}
                          className={`block rounded border border-dashed px-2 py-2 text-sm hover:bg-muted ${
                            selected ? "bg-muted ring-1 ring-primary" : ""
                          }`}
                        >
                          <span className="font-medium">{command.label}</span>
                          <span className="mt-0.5 block text-xs text-muted-foreground">
                            {command.description}
                          </span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ) : null}
              {query.trim() &&
              entitySearchLoading &&
              entityResults.length === 0 ? (
                <p
                  className="px-2 py-1 text-xs text-muted-foreground"
                  data-testid="commandbar-entity-loading"
                >
                  Поиск по сущностям…
                </p>
              ) : null}
              {entityGroups.length > 0 ? (
                <div data-testid="commandbar-entities">
                  {entityGroups.map((group) => (
                    <div key={group.entityType} className="mb-2 last:mb-0">
                      <div
                        className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                        data-entity-group={group.entityType}
                      >
                        {group.label}
                      </div>
                      <div className="space-y-1">
                        {group.items.map((item) => {
                          const path =
                            item.deeplink ??
                            `/search?q=${encodeURIComponent(query.trim())}`;
                          const navKey = `entity-${item.entity_type}-${item.entity_id}`;
                          const index = indexByKey.get(navKey) ?? -1;
                          const selected = index === selectedIndex;
                          return (
                            <Link
                              key={`${item.entity_type}-${item.entity_id}`}
                              to={path}
                              ref={(node) => {
                                if (index >= 0) itemRefs.current[index] = node;
                              }}
                              id={`commandbar-item-${navKey}`}
                              role="option"
                              aria-selected={selected}
                              data-entity-type={item.entity_type}
                              data-entity-id={item.entity_id}
                              data-selected={selected || undefined}
                              onClick={() => {
                                trackUxMetric("navigation_click", {
                                  source: "commandbar-entity",
                                  entity_type: item.entity_type,
                                });
                                rememberRecentEntity(item, path);
                                setOpen(false);
                              }}
                              className={`block rounded px-2 py-2 text-sm hover:bg-muted ${
                                selected ? "bg-muted ring-1 ring-primary" : ""
                              }`}
                            >
                              <span className="font-medium">{item.title}</span>
                              {item.snippet ? (
                                <span className="mt-0.5 block text-xs text-muted-foreground">
                                  {item.snippet}
                                </span>
                              ) : null}
                            </Link>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {visibleSavedSearches.length > 0 ? (
                <div data-testid="commandbar-saved">
                  <div className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Сохранённые запросы
                  </div>
                  <div className="space-y-1">
                    {visibleSavedSearches.map((saved) => {
                      const path = buildSavedSearchPath(saved);
                      const navKey = `saved-${saved.id}`;
                      const index = indexByKey.get(navKey) ?? -1;
                      const selected = index === selectedIndex;
                      return (
                        <Link
                          key={saved.id}
                          to={path}
                          ref={(node) => {
                            if (index >= 0) itemRefs.current[index] = node;
                          }}
                          id={`commandbar-item-${navKey}`}
                          role="option"
                          aria-selected={selected}
                          data-saved-id={saved.id}
                          data-selected={selected || undefined}
                          onClick={() => {
                            trackUxMetric("navigation_click", {
                              source: "commandbar-saved",
                              path,
                            });
                            setOpen(false);
                          }}
                          className={`block rounded px-2 py-2 text-sm hover:bg-muted ${
                            selected ? "bg-muted ring-1 ring-primary" : ""
                          }`}
                        >
                          <span className="font-medium">
                            {saved.name || saved.q || "Сохранённый поиск"}
                          </span>
                          {saved.q ? (
                            <span className="mt-0.5 block text-xs text-muted-foreground">
                              Запрос: {saved.q}
                              {Array.isArray(saved.types) &&
                              saved.types.length > 0
                                ? ` · ${saved.types.join(", ")}`
                                : ""}
                            </span>
                          ) : null}
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ) : null}
              {visibleRecentEntities.length > 0 ? (
                <div data-testid="commandbar-recent-entities">
                  <div className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Недавно открытые
                  </div>
                  <div className="space-y-1">
                    {visibleRecentEntities.map((recent) => {
                      const navKey = `recent-entity-${recent.entity_type}-${recent.entity_id}`;
                      const index = indexByKey.get(navKey) ?? -1;
                      const selected = index === selectedIndex;
                      const typeLabel =
                        ENTITY_TYPE_LABELS[recent.entity_type] ??
                        recent.entity_type;
                      return (
                        <Link
                          key={navKey}
                          to={recent.path}
                          ref={(node) => {
                            if (index >= 0) itemRefs.current[index] = node;
                          }}
                          id={`commandbar-item-${navKey}`}
                          role="option"
                          aria-selected={selected}
                          data-entity-type={recent.entity_type}
                          data-entity-id={recent.entity_id}
                          data-selected={selected || undefined}
                          onClick={() => {
                            trackUxMetric("navigation_click", {
                              source: "commandbar-recent-entity",
                              entity_type: recent.entity_type,
                            });
                            // Re-hoist on click — re-opened items should stay
                            // fresh at position 0 (and refresh their TTL).
                            rememberRecentEntity(
                              {
                                kind: "entity",
                                entity_type: recent.entity_type,
                                entity_id: recent.entity_id,
                                title: recent.title,
                              } as SearchItem,
                              recent.path,
                            );
                            setOpen(false);
                          }}
                          className={`block rounded px-2 py-2 text-sm hover:bg-muted ${
                            selected ? "bg-muted ring-1 ring-primary" : ""
                          }`}
                        >
                          <span className="font-medium">{recent.title}</span>
                          <span className="mt-0.5 block text-xs text-muted-foreground">
                            {typeLabel}
                          </span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ) : null}
              {groupedForDisplay.map((section) => (
                <div key={section.title}>
                  <div className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {section.title}
                  </div>
                  <div className="space-y-1">
                    {section.items.map((item) => {
                      const navKey = `nav-${item.id}`;
                      const index = indexByKey.get(navKey) ?? -1;
                      const selected = index === selectedIndex;
                      return (
                        <div
                          key={item.id}
                          className={`flex items-start justify-between rounded px-2 py-2 text-sm hover:bg-muted ${
                            selected ? "bg-muted ring-1 ring-primary" : ""
                          }`}
                          data-selected={selected || undefined}
                        >
                          <Link
                            to={item.path}
                            ref={(node) => {
                              if (index >= 0) itemRefs.current[index] = node;
                            }}
                            id={`commandbar-item-${navKey}`}
                            role="option"
                            aria-selected={selected}
                            onClick={() => {
                              rememberRecent(item.path);
                              trackUxMetric("navigation_click", {
                                source: "commandbar",
                                path: item.path,
                              });
                              trackUxMetric("time_to_first_action", {
                                source: "commandbar",
                              });
                              setOpen(false);
                            }}
                            className="min-w-0 flex-1"
                          >
                            <span className="font-medium">{item.label}</span>
                            {query.trim() ? (
                              <span className="mt-0.5 block text-xs text-muted-foreground">
                                {item.groupTitle}
                              </span>
                            ) : null}
                          </Link>
                          <button
                            type="button"
                            className="ml-2 rounded px-1 text-xs text-muted-foreground hover:text-foreground"
                            aria-label={
                              favoritePaths.includes(item.path)
                                ? "Убрать из избранного"
                                : "Добавить в избранное"
                            }
                            onClick={() => toggleFavorite(item.path)}
                          >
                            {favoritePaths.includes(item.path) ? "★" : "☆"}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
              {!filtered.length &&
              matchedCommands.length === 0 &&
              entityGroups.length === 0 &&
              !entitySearchLoading ? (
                <p className="px-2 py-3 text-sm text-muted-foreground">
                  Ничего не найдено
                </p>
              ) : null}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};
