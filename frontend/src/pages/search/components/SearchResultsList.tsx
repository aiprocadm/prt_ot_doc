import { Link } from "react-router-dom";

import type { SearchItem } from "@/api/search";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Button } from "@/components/ui/button";
import type { ApiError } from "@/types/dto/common";

const isExternalLink = (link: string) => /^https?:\/\//i.test(link);

type Props = {
  query: string;
  items: SearchItem[];
  loading: boolean;
  loadingMore: boolean;
  error: ApiError | null;
  canLoadMore: boolean;
  onRetry: () => void;
  onLoadMore: () => Promise<void>;
};

export const SearchResultsList = ({ query, items, loading, loadingMore, error, canLoadMore, onRetry, onLoadMore }: Props) => (
  <div className="space-y-2">
    {loading ? <LoadingScreen label="Загрузка результатов поиска" /> : null}
    {!loading && error ? <ErrorState error={error} onRetry={onRetry} /> : null}
    {!loading && !error && query.trim().length > 0 && items.length === 0 ? <EmptyState title="Ничего не найдено" description="Попробуйте изменить запрос или фильтры." /> : null}
    {!loading && !error
      ? items.map((item) => (
          <div key={`${item.entity_type}-${item.entity_id}`} className="rounded border p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-sm text-muted-foreground">{item.entity_type}</div>
                {item.deeplink && isExternalLink(item.deeplink) ? (
                  <a className="font-medium text-primary underline" href={item.deeplink} target="_blank" rel="noreferrer">
                    {item.title}
                  </a>
                ) : (
                  <Link className="font-medium text-primary underline" to={item.deeplink ?? "#"}>
                    {item.title}
                  </Link>
                )}
              </div>
              {item.status ? <div className="rounded-full border px-2 py-1 text-xs">{item.status}</div> : null}
            </div>
            {item.tags ? (
              <div className="mt-1 text-xs text-muted-foreground">{Object.entries(item.tags).slice(0, 4).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}</div>
            ) : null}
            {item.snippet ? <div className="mt-2 text-sm text-muted-foreground">{item.snippet}</div> : null}
          </div>
        ))
      : null}
    {canLoadMore ? (
      <Button onClick={() => void onLoadMore()} variant="outline" disabled={loadingMore}>
        {loadingMore ? "Загрузка..." : "Загрузить ещё"}
      </Button>
    ) : null}
  </div>
);
