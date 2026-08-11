import { useEffect } from "react";

import { HealthStatusPanel } from "@/components/health/HealthStatusPanel";
import { useHealthStore } from "@/stores/health";

export function HealthStatusPage() {
  const data = useHealthStore((state) => state.data);
  const loading = useHealthStore((state) => state.loading);
  const error = useHealthStore((state) => state.error);
  const fetchComprehensive = useHealthStore((state) => state.fetchComprehensive);

  useEffect(() => {
    void fetchComprehensive();
  }, [fetchComprehensive]);

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold">Состояние системы</h1>
        <p className="text-sm text-muted-foreground">
          Детальная диагностика по зависимостям: БД, кэш, хранилище, воркеры и интеграции.
        </p>
      </div>
      <HealthStatusPanel
        data={data}
        loading={loading}
        error={error}
        onRefresh={() => void fetchComprehensive({ skip_cache: true })}
      />
    </div>
  );
}

export default HealthStatusPage;
