import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/common/StatusBadge";
import { formatDate } from "@/utils/datetime";

import { useClientPortalPackages } from "./useClientPortalPackages";

const ClientPortalRequestsPage = () => {
  const { selected, loading, load } = useClientPortalPackages();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Кабинет клиента" }, { label: "Запросы" }]} />
        <Button variant="outline" onClick={() => void load()} disabled={loading}>Обновить</Button>
      </div>
      <Card>
        <CardHeader><CardTitle>Запросы и обращения</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {selected?.tickets.length ? selected.tickets.map((ticket) => (
            <div key={ticket.id} className="rounded-lg border p-4 text-sm">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium">{ticket.title}</div>
                <StatusBadge status={ticket.status} />
              </div>
              <div className="text-muted-foreground">Создан: {formatDate(ticket.created_at)}</div>
            </div>
          )) : <div className="text-sm text-muted-foreground">Открытых запросов пока нет.</div>}
        </CardContent>
      </Card>
    </div>
  );
};

export default ClientPortalRequestsPage;
