import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { formatDate } from "@/utils/datetime";

import { useClientPortalPackages } from "./useClientPortalPackages";

const ClientPortalHistoryPage = () => {
  const { selected, loading, error, load } = useClientPortalPackages();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <Breadcrumb
          items={[
            { label: "Главная", to: "/dashboard" },
            { label: "Кабинет клиента" },
            { label: "История" },
          ]}
        />
        <Button
          variant="outline"
          onClick={() => void load()}
          disabled={loading}
        >
          Обновить
        </Button>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      {loading ? <LoadingScreen label="Загрузка истории пакета" /> : null}
      {!loading && !error && !selected?.events.length ? (
        <EmptyState
          title="События отсутствуют"
          description="История появится после публикации пакета."
        />
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>События пакета</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!loading && !error && selected?.events.length
            ? selected.events.map((event) => (
                <div key={event.id} className="rounded-lg border p-4 text-sm">
                  <div className="font-medium">{event.type}</div>
                  <div className="text-muted-foreground">
                    {formatDate(event.created_at)}
                  </div>
                </div>
              ))
            : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default ClientPortalHistoryPage;
