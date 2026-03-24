import { useEffect, useState } from "react";

import { edoApi, type EdoEnvelope } from "@/api/edo";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ApiError } from "@/types/dto/common";

const EdoPage = () => {
  const [items, setItems] = useState<EdoEnvelope[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await edoApi.list());
    } catch (nextError) {
      setError((nextError as ApiError) ?? { status: 0, message: "Не удалось загрузить ЭДО сообщения" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "ЭДО" }]} />
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl font-semibold">ЭДО</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            Provider mode: non-production. Текущий контур использует internal/mock semantics и не должен восприниматься как боевой внешний ЭДО-оператор.
          </div>
          <ErrorState error={error ?? undefined} onRetry={() => void load()} />
          {loading ? <LoadingScreen label="Загрузка ЭДО сообщений" /> : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState
              title="ЭДО сообщения отсутствуют"
              description="После отправки документов сюда попадут envelopes, статусы и внешние идентификаторы."
            />
          ) : null}
          {!loading && !error && items.length > 0 ? (
            items.map((it) => (
              <div key={it.id} className="rounded border p-3 text-sm">
                <div>{it.id.slice(0, 8)} — {it.status}</div>
                <div className="text-muted-foreground">external_id: {it.external_id ?? "—"}</div>
              </div>
            ))
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default EdoPage;
