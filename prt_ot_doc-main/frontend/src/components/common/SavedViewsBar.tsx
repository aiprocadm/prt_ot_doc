import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export interface SavedView {
  id: string;
  name: string;
  params: Record<string, string>;
}

interface SavedViewsBarProps {
  storageKey: string;
  currentParams: URLSearchParams;
  onApply: (params: Record<string, string>) => void;
  title?: string;
}

const loadViews = (storageKey: string): SavedView[] => {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SavedView[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const persistViews = (storageKey: string, views: SavedView[]) => {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(storageKey, JSON.stringify(views));
};

const toRecord = (params: URLSearchParams) => {
  const result: Record<string, string> = {};
  params.forEach((value, key) => {
    if (value) result[key] = value;
  });
  return result;
};

export const SavedViewsBar = ({ storageKey, currentParams, onApply, title = "Сохранённые представления" }: SavedViewsBarProps) => {
  const [views, setViews] = useState<SavedView[]>([]);
  const [name, setName] = useState("");

  useEffect(() => {
    setViews(loadViews(storageKey));
  }, [storageKey]);

  const currentRecord = useMemo(() => toRecord(currentParams), [currentParams]);

  const saveCurrentView = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const next: SavedView = {
      id: `${Date.now()}`,
      name: trimmed,
      params: currentRecord,
    };
    const updated = [next, ...views].slice(0, 10);
    setViews(updated);
    setName("");
    persistViews(storageKey, updated);
  };

  const deleteView = (id: string) => {
    const updated = views.filter((view) => view.id !== id);
    setViews(updated);
    persistViews(storageKey, updated);
  };

  if (!views.length && !name) {
    return (
      <div className="rounded-md border bg-card p-3">
        <p className="mb-2 text-sm font-medium">{title}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Название текущего представления" className="max-w-sm" />
          <Button size="sm" variant="outline" onClick={saveCurrentView}>
            Сохранить вид
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-md border bg-card p-3">
      <p className="mb-2 text-sm font-medium">{title}</p>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Название текущего представления" className="max-w-sm" />
        <Button size="sm" variant="outline" onClick={saveCurrentView}>
          Сохранить вид
        </Button>
      </div>
      {views.length ? (
        <div className="flex flex-wrap gap-2">
          {views.map((view) => (
            <div key={view.id} className="flex items-center gap-1 rounded-full border px-2 py-1">
              <button type="button" className="text-xs text-primary underline-offset-4 hover:underline" onClick={() => onApply(view.params)}>
                {view.name}
              </button>
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-destructive"
                onClick={() => deleteView(view.id)}
                aria-label={`Удалить представление ${view.name}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
};
