import { Clock3, Trash2 } from "lucide-react";

import type { SavedSearchItem } from "@/api/search";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type RecentSearchItem = { id: string; q: string; types: string[] };

type Props = {
  recent: RecentSearchItem[];
  saved: SavedSearchItem[];
  onApplySavedSearch: (item: SavedSearchItem | RecentSearchItem) => void;
  onDeleteSavedSearch: (id: string) => Promise<void>;
};

export const SearchSidebar = ({
  recent,
  saved,
  onApplySavedSearch,
  onDeleteSavedSearch,
}: Props) => (
  <div className="space-y-4">
    <Card>
      <CardHeader>
        <CardTitle>Недавние запросы</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {recent.map((item) => (
          <button
            key={item.id}
            type="button"
            className="flex w-full items-start gap-2 rounded border p-3 text-left hover:bg-muted"
            onClick={() => onApplySavedSearch(item)}
          >
            <Clock3 className="mt-0.5 h-4 w-4 text-muted-foreground" />
            <div>
              <div className="font-medium">{item.q}</div>
              <div className="text-xs text-muted-foreground">
                {item.types.join(", ") || "all types"}
              </div>
            </div>
          </button>
        ))}
      </CardContent>
    </Card>
    <Card>
      <CardHeader>
        <CardTitle>Сохранённые поиски</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {saved.map((item) => (
          <div key={item.id} className="rounded border p-3">
            <div className="flex items-start justify-between gap-2">
              <button
                type="button"
                className="text-left"
                onClick={() => onApplySavedSearch(item)}
              >
                <div className="font-medium">{item.name}</div>
                <div className="text-xs text-muted-foreground">{item.q}</div>
                {Object.keys(item.filters ?? {}).length ? (
                  <div className="mt-1 text-xs text-muted-foreground">
                    filters:{" "}
                    {Object.entries(item.filters ?? {})
                      .map(([key, value]) => `${key}=${String(value)}`)
                      .join(", ")}
                  </div>
                ) : null}
              </button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => void onDeleteSavedSearch(item.id)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  </div>
);
