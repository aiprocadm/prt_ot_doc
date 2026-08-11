import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/utils/datetime";
import { entityContextPath, taskInboxLink } from "@/utils/workspaceNavigation";
import type { DashboardOperationalSnapshotDto } from "@/types/dto/dashboard";
import type { WorkspaceTaskInboxDto } from "@/api/workspace";

type Props = {
  taskInbox: WorkspaceTaskInboxDto;
  operational: DashboardOperationalSnapshotDto | null;
};

export const RecentObjectsSection = ({ taskInbox, operational }: Props) => (
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
);

