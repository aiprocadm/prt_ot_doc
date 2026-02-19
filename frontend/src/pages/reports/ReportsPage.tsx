import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { ErrorState } from "@/components/common/ErrorState";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type KpiPayload = {
  risks_high: number;
  trainings_overdue: number;
  ppe_issues_month: number;
  incidents_open: number;
  prescriptions_overdue: number;
};

const ReportsPage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [kpi, setKpi] = useState<KpiPayload | null>(null);

  const loadKpi = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await apiClient.get<KpiPayload>("/reports/kpi");
      setKpi(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить KPI");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadKpi();
  }, []);

  const cards = [
    { label: "Высокие риски", value: kpi?.risks_high ?? 0 },
    { label: "Просроченные обучения", value: kpi?.trainings_overdue ?? 0 },
    { label: "Выдачи СИЗ за месяц", value: kpi?.ppe_issues_month ?? 0 },
    { label: "Открытые инциденты", value: kpi?.incidents_open ?? 0 },
    { label: "Просроченные предписания", value: kpi?.prescriptions_overdue ?? 0 }
  ];

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Отчёты" }]} />
      <ErrorState error={error ?? undefined} onRetry={loadKpi} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((item) => (
          <Card key={item.label}>
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">{item.label}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-semibold">{loading ? "—" : item.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default ReportsPage;
