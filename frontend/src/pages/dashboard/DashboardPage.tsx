import { CalendarClock, Layers, ShieldAlert, Users2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { workspaceApi } from "@/api/workspace";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Can } from "@/components/permissions/Can";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RiskBadge } from "@/components/common/RiskBadge";
import { SlaIndicator } from "@/components/common/SlaIndicator";
import { StatusBadge } from "@/components/common/StatusBadge";
import { AttentionPanel } from "@/components/common/AttentionPanel";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { PERMISSIONS } from "@/permissions/permissions";
import { useDashboardStore } from "@/stores/dashboard";
import { formatDate } from "@/utils/datetime";
import { entityContextPath, taskInboxLink } from "@/utils/workspaceNavigation";

const trainingStatusLabels: Record<string, string> = {
  ok: "OK",
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
              <Button>Создать документ</Button>
            </Can>
            <Can
              permission={PERMISSIONS.DOCUMENT_CREATE}
              fallback={<Button variant="outline" disabled title="Недостаточно прав для запуска мастера">Запустить мастер</Button>}
            >
              <Button variant="outline">Запустить мастер</Button>
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

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Недавние объекты и черновики</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="rounded-md border bg-muted/20 p-4">
            <div className="mb-2 text-sm font-semibold">Последние задачи</div>
            {taskInbox.items.length ? (
              <ul className="space-y-2">
                {taskInbox.items.slice(0, 5).map((task) => (
                  <li key={task.id} className="text-sm">
                    <Link to={taskInboxLink(task)} className="font-medium text-blue-600 hover:underline">
                      {task.title}
                    </Link>
                    <div className="text-xs text-muted-foreground">
                      {task.overdue ? "Просрочено" : "В работе"} · {task.priority}
                    </div>
                    {entityContextPath(task.entity_type) ? (
                      <Link to={entityContextPath(task.entity_type) ?? "/tasks"} className="text-xs text-muted-foreground hover:underline">
                        Контекст: {task.entity_type}
                      </Link>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">Недавние задачи пока не найдены.</p>
            )}
            <div className="mt-3">
              <Button size="sm" variant="ghost" asChild>
                <Link to="/tasks">Открыть задачи</Link>
              </Button>
            </div>
          </div>

          <div className="rounded-md border bg-muted/20 p-4">
            <div className="mb-2 text-sm font-semibold">Последние документы</div>
            {operational?.documents.length ? (
              <ul className="space-y-2">
                {operational.documents.slice(0, 5).map((doc) => (
                  <li key={doc.id} className="text-sm">
                    <Link to="/pipelines/runs" className="font-medium text-blue-600 hover:underline">
                      {doc.title}
                    </Link>
                    <div className="text-xs text-muted-foreground">
                      {doc.route_label} · {formatDate(doc.created_at)}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">Недавние документы пока не найдены.</p>
            )}
            <div className="mt-3">
              <Button size="sm" variant="ghost" asChild>
                <Link to="/pipelines/runs">Открыть запуски</Link>
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="tasks">
        <TabsList>
          <TabsTrigger value="tasks">Единый inbox задач</TabsTrigger>
          <TabsTrigger value="documents">ЭДО-реестр</TabsTrigger>
          <TabsTrigger value="readiness">Готовность к проверке</TabsTrigger>
        </TabsList>
        <TabsContent value="tasks">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Задачи и SLA</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="text-sm text-muted-foreground">
                  Inbox: {taskInbox.total} задач, просрочено: {taskInbox.overdue}, показано: {filteredTaskInbox.length}
                </div>
                <div className="flex flex-wrap gap-2">
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                    <span className="text-muted-foreground">Статус</span>
                    <select
                      aria-label="Фильтр задач по статусу"
                      className="bg-transparent outline-none"
                      value={taskStatusFilter}
                      onChange={(event) => setTaskStatusFilter(event.target.value as "all" | "overdue" | "active")}
                    >
                      <option value="all">Все</option>
                      <option value="overdue">Просроченные</option>
                      <option value="active">Без просрочки</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                    <span className="text-muted-foreground">Приоритет</span>
                    <select
                      aria-label="Фильтр задач по приоритету"
                      className="bg-transparent outline-none"
                      value={taskPriorityFilter}
                      onChange={(event) => setTaskPriorityFilter(event.target.value as "all" | "critical_high" | "normal")}
                    >
                      <option value="all">Все</option>
                      <option value="critical_high">Critical / High</option>
                      <option value="normal">Medium / Low</option>
                    </select>
                  </div>
                </div>
              </div>
              <div data-testid="workspace-task-inbox">
                <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Задача</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead>Приоритет</TableHead>
                    <TableHead>Ответственный</TableHead>
                    <TableHead>Контекст</TableHead>
                    <TableHead>SLA</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {taskInboxLoading ? (
                    <TableRow>
                      <TableCell colSpan={7}>
                        <LoadingScreen label="Загрузка task inbox" />
                      </TableCell>
                    </TableRow>
                  ) : filteredTaskInbox.length ? filteredTaskInbox.map((task) => (
                    <TableRow key={task.id}>
                      <TableCell className="font-medium">{task.id.slice(0, 8)}</TableCell>
                      <TableCell>
                        <Link to={taskInboxLink(task)} className="font-medium text-blue-600 hover:underline">
                          {task.title}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={task.status} />
                      </TableCell>
                      <TableCell className="capitalize">{task.priority}</TableCell>
                      <TableCell>{task.assignee_id ? task.assignee_id.slice(0, 8) : "Не назначен"}</TableCell>
                      <TableCell>
                        {entityContextPath(task.entity_type) ? (
                          <Link to={entityContextPath(task.entity_type) ?? "/tasks"} className="text-blue-600 hover:underline">
                            {task.entity_type}
                          </Link>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <SlaIndicator
                          status={task.overdue ? "overdue" : task.priority === "critical" || task.priority === "high" ? "warning" : "ok"}
                          label={task.due_at ? `Срок: ${formatDate(task.due_at)}` : "Без срока"}
                        />
                      </TableCell>
                    </TableRow>
                  )) : (
                    <TableRow>
                      <TableCell colSpan={7}>
                        <EmptyState
                          title="Под выбранные фильтры задач нет"
                          description="Измените фильтры triage или дождитесь новых задач в workspace inbox."
                        />
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="documents">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Документы и маршруты</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Документ</TableHead>
                    <TableHead>Маршрут</TableHead>
                    <TableHead>Статус</TableHead>
                    <TableHead>Риск</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {operationalLoading ? (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <LoadingScreen label="Загрузка document pipeline snapshot" />
                      </TableCell>
                    </TableRow>
                  ) : operational?.documents.length ? operational.documents.map((doc) => (
                    <TableRow key={doc.id}>
                      <TableCell className="font-medium">{doc.id.slice(0, 8)}</TableCell>
                      <TableCell>{doc.title}</TableCell>
                      <TableCell>{doc.route_label}</TableCell>
                      <TableCell>
                        <StatusBadge status={doc.status} />
                      </TableCell>
                      <TableCell>
                        <RiskBadge level={doc.risk} />
                      </TableCell>
                    </TableRow>
                  )) : (
                    <TableRow>
                      <TableCell colSpan={5}>
                        <EmptyState
                          title="Запусков нет"
                          description="Последние document pipeline runs пока отсутствуют."
                        />
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="readiness">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Пакеты проверки</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <div className="rounded-md border bg-muted/30 p-4">
                <div className="text-sm font-semibold">Inspection prep readiness</div>
                <p className="mt-1 text-xs text-muted-foreground">
                  Пакетов: {operational?.readiness.packages_total ?? 0}, gaps: {operational?.readiness.open_gaps ?? 0}, критичных: {operational?.readiness.critical_gaps ?? 0}.
                </p>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" asChild>
                    <Link to="/audit-prep">Открыть сводку</Link>
                  </Button>
                  <Button size="sm" variant="outline" asChild>
                    <Link to="/inspection-prep">Пакеты проверки</Link>
                  </Button>
                </div>
              </div>
              <div className="rounded-md border bg-muted/30 p-4">
                <div className="text-sm font-semibold">Readiness score: {operational?.readiness.readiness_score ?? 0}%</div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {(operational?.readiness.reasons ?? ["Нет данных о readiness."]).join(" ")}
                </p>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="outline" asChild>
                    <Link to="/tasks?overdue=true">Открыть blockers</Link>
                  </Button>
                  <Button size="sm" variant="ghost" asChild>
                    <Link to="/prescriptions">Предписания</Link>
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default DashboardPage;
