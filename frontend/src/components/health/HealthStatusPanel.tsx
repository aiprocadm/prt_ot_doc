import { Activity, AlertTriangle, CheckCircle2, RefreshCw, XCircle, type LucideIcon } from "lucide-react";

import type { HealthCheckItem, HealthCheckStatus, HealthComprehensiveDto } from "@/api/health";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/utils/cn";

/** Human labels for the known dependency names returned by the backend. */
const CHECK_LABELS_RU: Record<string, string> = {
  postgres: "PostgreSQL",
  redis: "Redis",
  minio: "MinIO (S3)",
  workers: "Воркеры (Celery)",
  "1c_integration": "Интеграция 1С",
  edo_integration: "Интеграция ЭДО",
  email: "Email"
};

/** Surface problems first: failed → degraded → ok, then alphabetical. */
const STATUS_ORDER: Record<HealthCheckStatus, number> = { failed: 0, degraded: 1, ok: 2 };

const STATUS_ICON: Record<HealthCheckStatus, LucideIcon> = {
  ok: CheckCircle2,
  degraded: AlertTriangle,
  failed: XCircle
};

const STATUS_ICON_CLASS: Record<HealthCheckStatus, string> = {
  ok: "text-emerald-500",
  degraded: "text-amber-500",
  failed: "text-red-500"
};

export type HealthStatusPanelProps = {
  data: HealthComprehensiveDto | null;
  loading?: boolean;
  error?: { message?: string } | null;
  onRefresh?: () => void;
};

function CheckRow({ check }: { check: HealthCheckItem }) {
  const Icon = STATUS_ICON[check.status] ?? AlertTriangle;
  const label = CHECK_LABELS_RU[check.name] ?? check.name;
  return (
    <Card data-testid={`health-check-${check.name}`}>
      <CardContent className="flex items-start justify-between gap-4 p-4">
        <div className="flex items-start gap-3">
          <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", STATUS_ICON_CLASS[check.status])} aria-hidden />
          <div className="space-y-1">
            <div className="font-medium">{label}</div>
            {check.error ? (
              <p className="text-sm text-red-600" data-testid={`health-check-${check.name}-error`}>
                {check.error}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">{check.duration_ms.toFixed(0)} мс</p>
            )}
          </div>
        </div>
        <StatusBadge status={check.status} />
      </CardContent>
    </Card>
  );
}

/**
 * Per-dependency health drill-down (postgres/redis/minio/workers/integrations/
 * email). Pure presentational: data/loading/error come from props, so it is
 * unit-tested directly without mocking a store or the API client.
 */
export function HealthStatusPanel({ data, loading, error, onRefresh }: HealthStatusPanelProps) {
  const checks = data
    ? Object.values(data.checks).sort((a, b) => {
        const order = (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9);
        return order !== 0 ? order : a.name.localeCompare(b.name);
      })
    : [];

  return (
    <section className="space-y-4" data-testid="health-status-panel">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-muted-foreground" aria-hidden />
          <h2 className="text-lg font-semibold">Состояние системы</h2>
          {data ? <StatusBadge status={data.status} /> : null}
        </div>
        {onRefresh ? (
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} aria-hidden />
            Обновить
          </Button>
        ) : null}
      </header>

      {error ? (
        <Card data-testid="health-status-error">
          <CardContent className="p-4 text-sm text-red-600">
            Не удалось загрузить состояние системы{error.message ? `: ${error.message}` : "."}
          </CardContent>
        </Card>
      ) : null}

      {!error && checks.length === 0 ? (
        <Card>
          <CardContent className="p-4 text-sm text-muted-foreground">
            {loading ? "Загрузка состояния системы…" : "Нет данных о состоянии системы."}
          </CardContent>
        </Card>
      ) : null}

      {checks.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {checks.map((check) => (
            <CheckRow key={check.name} check={check} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

export default HealthStatusPanel;
