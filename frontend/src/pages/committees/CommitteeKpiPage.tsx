import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { committeesApi, type CommitteeKpi } from "@/api/committees";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ApiError } from "@/types/dto/common";

const asApiError = (err: unknown, fallback: string): ApiError =>
  err && typeof err === "object" && "message" in err
    ? (err as ApiError)
    : { status: 0, message: fallback };

// Метрика = подпись + значение. Проценты форматируем с одним знаком и «%».
interface Metric {
  label: string;
  value: string;
}

interface MetricGroup {
  title: string;
  metrics: Metric[];
}

const pct = (v: number): string => `${v.toFixed(1)} %`;

const buildGroups = (kpi: CommitteeKpi): MetricGroup[] => [
  {
    title: "Комитеты",
    metrics: [
      { label: "Всего комитетов", value: String(kpi.committees_total) },
      { label: "Активных", value: String(kpi.committees_active) },
    ],
  },
  {
    title: "Заседания",
    metrics: [
      { label: "Запланировано", value: String(kpi.meetings_planned) },
      { label: "Проведено", value: String(kpi.meetings_held) },
      { label: "Отменено", value: String(kpi.meetings_cancelled) },
    ],
  },
  {
    title: "Решения",
    metrics: [{ label: "Всего решений", value: String(kpi.decisions_total) }],
  },
  {
    title: "Задачи",
    metrics: [
      { label: "Всего задач", value: String(kpi.tasks_total) },
      { label: "Открытые", value: String(kpi.tasks_open) },
      { label: "Просроченные", value: String(kpi.tasks_overdue) },
      { label: "Выполненные", value: String(kpi.tasks_done) },
    ],
  },
  {
    title: "Явка и кворум",
    metrics: [
      { label: "Средняя явка", value: pct(kpi.avg_attendance_pct) },
      { label: "Доля кворума", value: pct(kpi.quorum_rate_pct) },
      {
        label: "Проведённых заседаний (база)",
        value: String(kpi.held_meetings),
      },
    ],
  },
];

const MetricCard = ({ group }: { group: MetricGroup }) => (
  <Card>
    <CardHeader>
      <CardTitle className="text-base">{group.title}</CardTitle>
    </CardHeader>
    <CardContent>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {group.metrics.map((m) => (
          <div
            key={m.label}
            className="rounded-lg border border-border bg-background p-4 shadow-sm"
          >
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              {m.label}
            </p>
            <p className="mt-2 text-2xl font-semibold text-foreground">
              {m.value}
            </p>
          </div>
        ))}
      </div>
    </CardContent>
  </Card>
);

const backLink = (
  <Link to="/committees" className="text-sm text-primary hover:underline">
    ← К комитетам
  </Link>
);

const CommitteeKpiPage = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [kpi, setKpi] = useState<CommitteeKpi | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    committeesApi
      .getKpi()
      .then((data) => {
        if (alive) setKpi(data);
      })
      .catch((err) => {
        if (alive)
          setError(asApiError(err, "Не удалось загрузить KPI комитетов."));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (loading) return <LoadingScreen label="Загрузка KPI комитетов" />;

  // Флаг модуля выключен → бэкенд отвечает 404. Показываем понятную заглушку,
  // а не «сырую» ошибку.
  if (error && error.status === 404) {
    return (
      <div className="space-y-4">
        <RegistryPageHeader title="KPI комитетов" actions={backLink} />
        <EmptyState
          title="Модуль комитетов отключён"
          description="Обратитесь к администратору, чтобы включить модуль комитетов для вашей организации."
        />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <RegistryPageHeader title="KPI комитетов" actions={backLink} />
        <ErrorState error={error} />
      </div>
    );
  }

  const groups = kpi ? buildGroups(kpi) : [];

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="KPI комитетов"
        description="Показатели исполнения по комитетам: заседания, решения, задачи, явка и кворум."
        actions={backLink}
      />
      {groups.length === 0 ? (
        <EmptyState
          title="Данные отсутствуют"
          description="Пока нет данных для расчёта показателей."
        />
      ) : (
        groups.map((group) => <MetricCard key={group.title} group={group} />)
      )}
    </div>
  );
};

export default CommitteeKpiPage;
