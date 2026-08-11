import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Info,
  RefreshCw,
  type LucideIcon
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type {
  AlertCategory,
  AlertItem,
  AlertSeverity,
  OperationalDashboardDto
} from "@/api/operationalDashboard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/utils/cn";

const CATEGORY_LABELS_RU: Record<AlertCategory, string> = {
  overdue: "Просроченные",
  blocked_approval: "Заблокированные согласования",
  integration_error: "Ошибки интеграций",
  high_risk: "Высокий риск",
  health_warning: "Предупреждения системы",
  unassigned_task: "Неназначенные задачи",
  data_quality: "Качество данных",
  committee_task: "Задачи комитетов"
};

/** Canonical fallback order for categories with equal worst-severity. */
const CATEGORY_ORDER: AlertCategory[] = [
  "overdue",
  "blocked_approval",
  "integration_error",
  "high_risk",
  "health_warning",
  "unassigned_task",
  "data_quality",
  "committee_task"
];

const SEVERITY_RANK: Record<AlertSeverity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3
};

const SEVERITY_LABELS_RU: Record<AlertSeverity, string> = {
  critical: "Критичные",
  high: "Высокие",
  medium: "Средние",
  low: "Низкие"
};

const SEVERITY_ICON: Record<AlertSeverity, LucideIcon> = {
  critical: AlertCircle,
  high: AlertTriangle,
  medium: Info,
  low: Info
};

const SEVERITY_ICON_CLASS: Record<AlertSeverity, string> = {
  critical: "text-red-500",
  high: "text-amber-500",
  medium: "text-muted-foreground",
  low: "text-muted-foreground"
};

const SEVERITY_SUMMARY_ORDER: AlertSeverity[] = ["critical", "high", "medium", "low"];

const MAX_VISIBLE_PER_CATEGORY = 20;

const isInternalUrl = (url?: string | null): url is string => Boolean(url && url.startsWith("/"));

type CategoryGroup = { category: AlertCategory; alerts: AlertItem[] };

function groupByCategory(alerts: AlertItem[]): CategoryGroup[] {
  const map = new Map<AlertCategory, AlertItem[]>();
  for (const alert of alerts) {
    const list = map.get(alert.category) ?? [];
    list.push(alert);
    map.set(alert.category, list);
  }
  const groups: CategoryGroup[] = Array.from(map.entries()).map(([category, items]) => ({
    category,
    alerts: [...items].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])
  }));
  groups.sort((a, b) => {
    const aWorst = Math.min(...a.alerts.map((i) => SEVERITY_RANK[i.severity]));
    const bWorst = Math.min(...b.alerts.map((i) => SEVERITY_RANK[i.severity]));
    if (aWorst !== bWorst) return aWorst - bWorst;
    return CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category);
  });
  return groups;
}

function AlertRow({ alert }: { alert: AlertItem }) {
  const Icon = SEVERITY_ICON[alert.severity] ?? Info;
  return (
    <div className="flex items-start gap-3 rounded-md border bg-muted/30 p-3" data-testid={`cc-alert-${alert.id}`}>
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", SEVERITY_ICON_CLASS[alert.severity])} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{alert.title}</span>
          <Badge variant="secondary" className="text-xs">
            {alert.count} шт.
          </Badge>
        </div>
        {alert.description ? <p className="mt-0.5 text-xs text-muted-foreground">{alert.description}</p> : null}
        {isInternalUrl(alert.action_url) ? (
          <Link
            to={alert.action_url}
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:underline"
          >
            Перейти <ArrowRight className="h-3 w-3" />
          </Link>
        ) : null}
      </div>
    </div>
  );
}

function AlertCategoryCard({ category, alerts }: CategoryGroup) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? alerts : alerts.slice(0, MAX_VISIBLE_PER_CATEGORY);
  const hidden = alerts.length - visible.length;
  return (
    <Card data-testid={`cc-category-${category}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{CATEGORY_LABELS_RU[category] ?? category}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {visible.map((alert) => (
          <AlertRow key={alert.id} alert={alert} />
        ))}
        {hidden > 0 ? (
          <Button variant="ghost" size="sm" onClick={() => setExpanded(true)}>
            Показать ещё ({hidden})
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

export type CommandCenterPanelProps = {
  data: OperationalDashboardDto | null;
  loading?: boolean;
  error?: { message?: string } | null;
  onRefresh?: () => void;
};

/**
 * Pure presentational command center: data/loading/error come from props, so it
 * is unit-tested directly without mocking a store or the API client.
 */
export function CommandCenterPanel({ data, loading, error, onRefresh }: CommandCenterPanelProps) {
  const groups = data ? groupByCategory(data.alerts) : [];

  return (
    <section className="space-y-4" data-testid="command-center-panel">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">Командный центр</h2>
          {data ? <StatusBadge status={data.status} /> : null}
        </div>
        {onRefresh ? (
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} aria-hidden />
            Обновить
          </Button>
        ) : null}
      </header>

      {data ? (
        <div className="flex flex-wrap gap-2" data-testid="cc-severity-summary">
          {SEVERITY_SUMMARY_ORDER.map((sev) => {
            const n = data.alert_count?.[sev] ?? 0;
            if (!n) return null;
            return (
              <Badge
                key={sev}
                variant={sev === "critical" ? "destructive" : "secondary"}
                className="text-xs"
              >
                {SEVERITY_LABELS_RU[sev]}: {n}
              </Badge>
            );
          })}
        </div>
      ) : null}

      {error ? (
        <Card data-testid="command-center-error">
          <CardContent className="p-4 text-sm text-red-600">
            Не удалось загрузить командный центр{error.message ? `: ${error.message}` : "."}
          </CardContent>
        </Card>
      ) : null}

      {!error && data && data.alerts.length === 0 ? (
        <Card data-testid="command-center-empty">
          <CardContent className="flex items-center gap-2 p-4 text-sm text-emerald-600">
            <CheckCircle2 className="h-4 w-4" aria-hidden />
            Нет активных алертов
          </CardContent>
        </Card>
      ) : null}

      {!error && !data && loading ? (
        <Card>
          <CardContent className="p-4 text-sm text-muted-foreground">Загрузка командного центра…</CardContent>
        </Card>
      ) : null}

      {groups.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {groups.map((group) => (
            <AlertCategoryCard key={group.category} category={group.category} alerts={group.alerts} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

export default CommandCenterPanel;
