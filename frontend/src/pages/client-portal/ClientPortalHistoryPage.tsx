import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/utils/datetime";

import { useClientPortalPackages } from "./useClientPortalPackages";

const ClientPortalHistoryPage = () => {
  const { selected, loading, load } = useClientPortalPackages();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Кабинет клиента" }, { label: "История" }]} />
        <Button variant="outline" onClick={() => void load()} disabled={loading}>Обновить</Button>
      </div>
      <Card>
        <CardHeader><CardTitle>События пакета</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {selected?.events.length ? selected.events.map((event) => (
            <div key={event.id} className="rounded-lg border p-4 text-sm">
              <div className="font-medium">{event.type}</div>
              <div className="text-muted-foreground">{formatDate(event.created_at)}</div>
            </div>
          )) : <div className="text-sm text-muted-foreground">История событий появится после публикации пакета.</div>}
        </CardContent>
      </Card>
    </div>
  );
};

export default ClientPortalHistoryPage;
