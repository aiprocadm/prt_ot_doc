import { CalendarClock, Layers, ShieldAlert, Users2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { workspaceApi } from "@/api/workspace";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Can } from "@/components/permissions/Can";
import { ErrorState } from "@/components/common/ErrorState";
import { StatusBadge } from "@/components/common/StatusBadge";
import { AttentionPanel } from "@/components/common/AttentionPanel";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { PERMISSIONS } from "@/permissions/permissions";
import { useDashboardStore } from "@/stores/dashboard";
import { RecentObjectsSection } from "@/widgets/dashboard/RecentObjectsSection";
import { DashboardTabsSection } from "@/widgets/dashboard/DashboardTabsSection";

const trainingStatusLabels: Record<string, string> = {
  ok: "В норме",
  warning: "Нужны действия",
  critical: "Критично"
};

export const DashboardPage = () => {
  const [taskStatusFilter, setTaskStatusFilter] = useState<"all" | "overdue" | "active">("all");
  const [taskPriorityFilter, setTaskPriorityFilter] = useState<"all" | "critical_high" | "normal">("all");
  const {
    summary,
    operational,
    loading,
    operationalLoading,
    error,
    operationalError,
    fetchSummary,
    fetchOperational
  } = useDashboardStore();

  const loadTaskInbox = useCallback(() => workspaceApi.getTaskInbox(50, 0), []);
  const {
    data: taskInbox,
    loading: taskInboxLoading,
    error: taskInboxError,
    reload: reloadTaskInbox
  } = useAsyncResource({
    loader: loadTaskInbox,
    initialData: { total: 0, overdue: 0, items: [] },
    errorMessage: "Не удалось загрузить workspace task inbox"
  });

  useEffect(() => {
    fetchSummary();
    fetchOperational();
  }, [fetchOperational, fetchSummary]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      if (error) void fetchSummary();
      if (operationalError) void fetchOperational();
      if (taskInboxError) void reloadTaskInbox();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [error, operationalError, taskInboxError, fetchOperational, fetchSummary, reloadTaskInbox]);

  const trainingStatus = summary?.training.status ?? "ok";
  const trainingLabel = trainingStatusLabels[trainingStatus] ?? trainingStatus;

  const filteredTaskInbox = useMemo(() => {
    return taskInbox.items.filter((task) => {
      if (taskStatusFilter === "overdue" && !task.overdue) return false;
      if (taskStatusFilter === "active" && task.overdue) return false;
      if (taskPriorityFilter === "critical_high" && !["critical", "high"].includes(task.priority)) return false;
      if (taskPriorityFilter === "normal" && ["critical", "high"].includes(task.priority)) return false;
      return true;
    });
  }, [taskInbox.items, taskPriorityFilter, taskStatusFilter]);

  const kpis = [
    {
      label: "Просроченные задачи",
      value: loading ? "—" : summary?.overdue_tasks ?? 0,
      trend: `Критичных обязательств: ${summary?.critical_obligations ?? 0}`,
      icon: CalendarClock,
      href: "/tasks?overdue=true"
    },
    {
      label: "Критичные обязательства",
      value: loading ? "—" : summary?.critical_obligations ?? 0,
      trend: "Приоритет: критичный/высокий",
      icon: Layers,
      href: "/tasks?priority=critical"
    },
    {
      label: "Инциденты и риски",
      value: loading ? "—" : `${summary?.incidents_open ?? 0} / ${summary?.risks_total ?? 0}`,
      trend: "Активные инциденты / оценённые риски",
      icon: ShieldAlert,
      href: "/incidents"
    },
    {
      label: "Статус обучения",
      value: loading ? "—" : <StatusBadge status={trainingStatus} />,
      trend: `Просрочено: ${summary?.training.overdue ?? 0}, скоро: ${summary?.training.due_soon ?? 0}`,
      icon: Users2,
      href: "/training",
      helper: trainingLabel
    }
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <Breadcrumb items={[{ label: "Главная" }]} />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">Единый рабочий стол ОТ/ПБ</h1>
            <p className="text-sm text-muted-foreground">
              Контроль задач, ЭДО, рисков и готовности к проверкам по текущему тенанту.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Can
              permission={PERMISSIONS.DOCUMENT_CREATE}
              fallback={<Button disabled title="Недостаточно прав для создания документа">Создать документ</Button>}
            >
              <Button asChild>
                <Link to="/documents/wizard">Создать документ</Link>
              </Button>
            </Can>
            <Can
              permission={PERMISSIONS.PACK_VIEW}
              fallback={<Button variant="outline" disabled title="Недостаточно прав для запуска мастера">Запустить мастер</Button>}
            >
              <Button variant="outline" asChild>
                <Link to="/packs">Запустить мастер</Link>
              </Button>
            </Can>
          </div>
        </div>
      </div>

      <ErrorState error={error ?? undefined} onRetry={fetchSummary} />
      <ErrorState error={operationalError ?? undefined} onRetry={fetchOperational} />
      <ErrorState error={taskInboxError ?? undefined} onRetry={() => void reloadTaskInbox()} />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {kpis.map((item) => (
          <Card key={item.label} className="transition hover:shadow-md">
            {item.href ? (
              <Link to={item.href} className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <CardContent className="space-y-3 py-6">
                  <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>{item.label}</span>
                    <item.icon className="h-4 w-4" />
                  </div>
                  <div className="text-2xl font-semibold">{item.value}</div>
                  <div className="text-xs text-muted-foreground">
                    {item.helper ? `${item.helper} · ${item.trend}` : item.trend}
                  </div>
                </CardContent>
              </Link>
            ) : (
              <CardContent className="space-y-3 py-6">
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <span>{item.label}</span>
                  <item.icon className="h-4 w-4" />
                </div>
                <div className="text-2xl font-semibold">{item.value}</div>
                <div className="text-xs text-muted-foreground">{item.trend}</div>
              </CardContent>
            )}
          </Card>
        ))}
      </div>

      <AttentionPanel />

      <RecentObjectsSection taskInbox={taskInbox} operational={operational} />
      <DashboardTabsSection
        taskInbox={taskInbox}
        filteredTaskInbox={filteredTaskInbox}
        taskInboxLoading={taskInboxLoading}
        taskStatusFilter={taskStatusFilter}
        taskPriorityFilter={taskPriorityFilter}
        setTaskStatusFilter={setTaskStatusFilter}
        setTaskPriorityFilter={setTaskPriorityFilter}
        operational={operational}
        operationalLoading={operationalLoading}
      />
    </div>
  );
};

export default DashboardPage;
