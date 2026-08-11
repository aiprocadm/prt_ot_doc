import { useCallback, useEffect, useState } from "react";

import { dashboardApiClient } from "@/api/dashboardApi";
import { JsonKpiGrid } from "@/components/analytics/JsonKpiGrid";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import type { ApiError } from "@/types/dto/common";

type DashboardApiPageProps = {
  title: string;
  endpoint: string;
};

export const DashboardApiPage = ({ title, endpoint }: DashboardApiPageProps) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dashboardApiClient.getByEndpoint(endpoint);
      setPayload(data);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить данные" });
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    void load();
  }, [load]);

  const hasPayload = Object.keys(payload ?? {}).length > 0;

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: title }]} />
      <ErrorState error={error ?? undefined} onRetry={load} />
      {loading ? <LoadingScreen label="Загрузка дашборда" /> : null}
      {!loading && !error && !hasPayload ? (
        <EmptyState
          title="Данные дашборда отсутствуют"
          description="После появления операционных событий здесь будут рассчитаны ключевые показатели и индикаторы выполнения."
        />
      ) : null}
      {!loading && !error && hasPayload ? <JsonKpiGrid payload={payload} loading={loading} /> : null}
    </div>
  );
};
