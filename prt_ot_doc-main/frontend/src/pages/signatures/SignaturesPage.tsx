import { useEffect, useState } from "react";

import { signApi, type SignatureRequest } from "@/api/sign";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ApiError } from "@/types/dto/common";

const SignaturesPage = () => {
  const [items, setItems] = useState<SignatureRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await signApi.list());
    } catch (nextError) {
      setError((nextError as ApiError) ?? { status: 0, message: "Не удалось загрузить запросы на подпись" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="space-y-4">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Подписи" }]} />
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl font-semibold">Подписи</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            Provider mode зависит от configured signing adapter. Для `stub` и `internal-fallback` этот контур остаётся non-production и подходит только для внутренней оркестрации и тестовых сценариев.
          </div>
          <ErrorState error={error ?? undefined} onRetry={() => void load()} />
          {loading ? <LoadingScreen label="Загрузка запросов на подпись" /> : null}
          {!loading && !error && items.length === 0 ? (
            <EmptyState
              title="Запросы на подпись отсутствуют"
              description="После запуска согласования или подписи здесь появятся статусы, провайдер и дальнейшие действия."
            />
          ) : null}
          {!loading && !error && items.length > 0 ? (
            items.map((it) => (
              <div key={it.id} className="rounded border p-3 text-sm">
                <div>{it.id.slice(0, 8)} — {it.status}</div>
                <div className="text-muted-foreground">provider: {it.provider}</div>
              </div>
            ))
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default SignaturesPage;
