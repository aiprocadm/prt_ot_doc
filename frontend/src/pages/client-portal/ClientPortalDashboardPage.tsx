import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/common/StatusBadge";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";

import { useClientPortalPackages } from "./useClientPortalPackages";

const ClientPortalDashboardPage = () => {
  const { items, loading, error, load, summary } = useClientPortalPackages();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <Breadcrumb
          items={[
            { label: "Главная", to: "/dashboard" },
            { label: "Кабинет клиента" },
            { label: "Сводка" },
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
      {loading ? <LoadingScreen label="Загрузка сводки клиента" /> : null}
      {!loading && !error && !items.length ? (
        <EmptyState
          title="Пакеты не найдены"
          description="Пакеты появятся после публикации нового запуска."
        />
      ) : null}
      <div className="grid gap-4 md:grid-cols-5">
        <Card>
          <CardHeader>
            <CardTitle>Пакеты</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {summary.packagesTotal}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Файлы</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {summary.filesTotal}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>События</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {summary.eventsTotal}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Запросы</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {summary.requestsTotal}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Открытые требования</CardTitle>
          </CardHeader>
          <CardContent className="text-3xl font-semibold text-destructive">
            {summary.openRequirements}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Статусы пакетов</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!loading && !error && items.length
            ? items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between rounded-lg border p-3 text-sm"
                >
                  <div>{item.id}</div>
                  <StatusBadge status={item.status} />
                </div>
              ))
            : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default ClientPortalDashboardPage;
