import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/common/StatusBadge";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { formatDate } from "@/utils/datetime";

import { useClientPortalPackages } from "./useClientPortalPackages";

const ClientPortalRequestsPage = () => {
  const { selected, loading, error, load } = useClientPortalPackages();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Кабинет клиента" }, { label: "Запросы" }]} />
        <Button variant="outline" onClick={() => void load()} disabled={loading}>Обновить</Button>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      {loading ? <LoadingScreen label="Загрузка запросов клиента" /> : null}
      {!loading && !error && !selected?.tickets.length ? (
        <EmptyState title="Открытых запросов нет" description="Новые обращения и комментарии к пакету появятся здесь." />
      ) : null}
      <Card>
        <CardHeader><CardTitle>Запросы и обращения</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {!loading && !error && selected?.tickets.length ? selected.tickets.map((ticket) => (
            <div key={ticket.id} className="rounded-lg border p-4 text-sm">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium">{ticket.title}</div>
                <StatusBadge status={ticket.status} />
              </div>
              <div className="text-muted-foreground">Создан: {formatDate(ticket.created_at)}</div>
            </div>
          )) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default ClientPortalRequestsPage;
