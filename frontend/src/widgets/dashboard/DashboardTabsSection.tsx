import { Link } from "react-router-dom";

import { EmptyState } from "@/components/common/EmptyState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RiskBadge } from "@/components/common/RiskBadge";
import { SlaIndicator } from "@/components/common/SlaIndicator";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { WorkspaceTaskInboxDto } from "@/api/workspace";
import type { DashboardOperationalSnapshotDto } from "@/types/dto/dashboard";
import { formatDate } from "@/utils/datetime";
import { entityContextPath, taskInboxLink } from "@/utils/workspaceNavigation";

type Props = {
  taskInbox: WorkspaceTaskInboxDto;
  filteredTaskInbox: WorkspaceTaskInboxDto["items"];
  taskInboxLoading: boolean;
  taskStatusFilter: "all" | "overdue" | "active";
  taskPriorityFilter: "all" | "critical_high" | "normal";
  setTaskStatusFilter: (value: "all" | "overdue" | "active") => void;
  setTaskPriorityFilter: (value: "all" | "critical_high" | "normal") => void;
  operational: DashboardOperationalSnapshotDto | null;
  operationalLoading: boolean;
};

export const DashboardTabsSection = ({
  taskInbox,
  filteredTaskInbox,
  taskInboxLoading,
  taskStatusFilter,
  taskPriorityFilter,
  setTaskStatusFilter,
  setTaskPriorityFilter,
  operational,
  operationalLoading,
}: Props) => (
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
              Inbox: {taskInbox.total} задач, просрочено: {taskInbox.overdue},
              показано: {filteredTaskInbox.length}
            </div>
            <div className="flex flex-wrap gap-2">
              <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                <span className="text-muted-foreground">Статус</span>
                <select
                  aria-label="Фильтр задач по статусу"
                  className="bg-transparent outline-none"
                  value={taskStatusFilter}
                  onChange={(event) =>
                    setTaskStatusFilter(
                      event.target.value as "all" | "overdue" | "active",
                    )
                  }
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
                  onChange={(event) =>
                    setTaskPriorityFilter(
                      event.target.value as "all" | "critical_high" | "normal",
                    )
                  }
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
                      <LoadingScreen label="Загрузка входящих задач" />
                    </TableCell>
                  </TableRow>
                ) : filteredTaskInbox.length ? (
                  filteredTaskInbox.map((task) => (
                    <TableRow key={task.id}>
                      <TableCell className="font-medium">
                        {task.id.slice(0, 8)}
                      </TableCell>
                      <TableCell>
                        <Link
                          to={taskInboxLink(task)}
                          className="font-medium text-blue-600 hover:underline"
                        >
                          {task.title}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={task.status} />
                      </TableCell>
                      <TableCell className="capitalize">
                        {task.priority}
                      </TableCell>
                      <TableCell>
                        {task.assignee_id
                          ? task.assignee_id.slice(0, 8)
                          : "Не назначен"}
                      </TableCell>
                      <TableCell>
                        {entityContextPath(task.entity_type) ? (
                          <Link
                            to={entityContextPath(task.entity_type) ?? "/tasks"}
                            className="text-blue-600 hover:underline"
                          >
                            {task.entity_type}
                          </Link>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <SlaIndicator
                          status={
                            task.overdue
                              ? "overdue"
                              : task.priority === "critical" ||
                                  task.priority === "high"
                                ? "warning"
                                : "ok"
                          }
                          label={
                            task.due_at
                              ? `Срок: ${formatDate(task.due_at)}`
                              : "Без срока"
                          }
                        />
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={7}>
                      <EmptyState
                        title="Под выбранные фильтры задач нет"
                        description="Измените фильтры приоритизации или дождитесь новых задач во входящих."
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
                    <LoadingScreen label="Загрузка сводки по документам и маршрутам" />
                  </TableCell>
                </TableRow>
              ) : operational?.documents.length ? (
                operational.documents.map((doc) => (
                  <TableRow key={doc.id}>
                    <TableCell className="font-medium">
                      {doc.id.slice(0, 8)}
                    </TableCell>
                    <TableCell>{doc.title}</TableCell>
                    <TableCell>{doc.route_label}</TableCell>
                    <TableCell>
                      <StatusBadge status={doc.status} />
                    </TableCell>
                    <TableCell>
                      <RiskBadge level={doc.risk} />
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={5}>
                    <EmptyState
                      title="Запусков нет"
                      description="Последние запуски конвейера документов пока отсутствуют."
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
            <div className="text-sm font-semibold">
              Готовность к инспекционной подготовке
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Пакетов: {operational?.readiness.packages_total ?? 0}, пробелов:{" "}
              {operational?.readiness.open_gaps ?? 0}, критичных:{" "}
              {operational?.readiness.critical_gaps ?? 0}.
            </p>
            <div className="mt-3 flex gap-2">
              <Button size="sm" asChild>
                <Link to="/audit-prep">Открыть сводку</Link>
              </Button>
              <Button size="sm" variant="outline" asChild>
                <Link to="/inspection-prep/packages">Пакеты проверки</Link>
              </Button>
            </div>
          </div>
          <div className="rounded-md border bg-muted/30 p-4">
            <div className="text-sm font-semibold">
              Индекс готовности: {operational?.readiness.readiness_score ?? 0}%
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {(
                operational?.readiness.reasons ?? ["Нет данных о readiness."]
              ).join(" ")}
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
);
