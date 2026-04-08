import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { packsApi } from "@/api/packs";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ApiError } from "@/types/dto/common";

interface RunItem {
  id: string;
  row_no: number;
  status: string;
  file_name: string;
  error_code?: string;
}

const PackRunDetailsPage = () => {
  const { id = "" } = useParams();
  const [items, setItems] = useState<RunItem[]>([]);
  const [timeline, setTimeline] = useState<Array<{ id: string; level: string; message: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [itemResp, timelineResp] = await Promise.all([
        packsApi.getRunItems<RunItem>(id),
        packsApi.getRunTimeline<{ id: string; level: string; message: string }>(id)
      ]);
      setItems(itemResp);
      setTimeline(timelineResp);
    } catch (loadError) {
      setItems([]);
      setTimeline([]);
      setError(loadError as ApiError);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [id]);

  const retryFailed = async () => {
    try {
      setError(null);
      await packsApi.retryFailedRunItems(id);
      await load();
    } catch (retryError) {
      setError(retryError as ApiError);
    }
  };

  if (loading) {
    return <LoadingScreen label="Загрузка запуска пакета" />;
  }

  return (
    <div className="space-y-4">
      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      <Card>
        <CardHeader>
          <CardTitle>Строки запуска пакета</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Button variant="outline" onClick={() => void retryFailed()}>Повторить сбойные</Button>
          {items.length === 0 ? (
            <EmptyState
              title="Строк запуска пакета нет"
              description="Для этого запуска ещё нет строк или они недоступны в текущей области тенанта."
            />
          ) : (
            items.map((item) => (
              <div key={item.id}>{item.row_no}. {item.file_name} — {item.status}</div>
            ))
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Хронология</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          {timeline.length === 0 ? (
            <EmptyState
              title="Хронология пуста"
              description="События выполнения появятся после старта или повторного запуска обработки."
            />
          ) : (
            timeline.map((entry) => (
              <div key={entry.id}>{entry.level}: {entry.message}</div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default PackRunDetailsPage;
