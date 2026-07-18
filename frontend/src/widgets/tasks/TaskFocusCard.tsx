import { Link } from "react-router-dom";

import { ActionButton } from "@/components/permissions/ActionButton";
import { Button } from "@/components/ui/button";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ApiError } from "@/types/dto/common";
import type { TaskDto } from "@/types/dto/tasks";
import { entityCardLink, entityContextPath } from "@/utils/workspaceNavigation";

type Props = {
  focusedTaskId?: string;
  focusedTask: TaskDto | null;
  focusLoadError?: ApiError | null;
  focusedEntityType?: string;
  focusedEntityId?: string;
  onCloseTask: (taskId: string) => void;
};

const isFocusTaskUnavailable = (err: ApiError | null | undefined) =>
  Boolean(
    err &&
      (err.status === 404 || err.code === "OBLIGATION_TASK_NOT_FOUND")
  );

export const TaskFocusCard = ({
  focusedTaskId,
  focusedTask,
  focusLoadError = null,
  focusedEntityType,
  focusedEntityId,
  onCloseTask
}: Props) => {
  if (!focusedTaskId) return null;

  const focusUnavailable = isFocusTaskUnavailable(focusLoadError);

  const summaryLink = entityCardLink(focusedTask?.entity_type ?? focusedEntityType, focusedTask?.entity_id ?? focusedEntityId, "summary");
  const timelineLink = entityCardLink(focusedTask?.entity_type ?? focusedEntityType, focusedTask?.entity_id ?? focusedEntityId, "timeline");
  const contextPath = entityContextPath(focusedTask?.entity_type ?? focusedEntityType) ?? "/tasks";

  return (
    <div className="mb-4 rounded-md border bg-muted/20 p-4" data-testid="task-focus-card">
      <div className="text-sm font-semibold">Фокус задачи из рабочего пространства</div>
      <p className="mt-1 text-xs text-muted-foreground">
        {focusedTask
          ? `${focusedTask.title} · ${focusedTask.status} · ${focusedTask.priority}`
          : focusUnavailable
            ? "Задача недоступна или не найдена в этом контуре."
            : `Задача ${focusedTaskId.slice(0, 8)} загружается...`}
      </p>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        {focusedTask?.entity_type || focusedEntityType ? (
          <span className="rounded border px-2 py-1">
            entity_type: {focusedTask?.entity_type ?? focusedEntityType}
          </span>
        ) : null}
        {focusedTask?.entity_id || focusedEntityId ? (
          <span className="rounded border px-2 py-1">
            entity_id: {(focusedTask?.entity_id ?? focusedEntityId)?.slice(0, 12)}
          </span>
        ) : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <ActionButton
          size="sm"
          variant="outline"
          permission={PERMISSIONS.TASK_UPDATE}
          onClick={() => {
            if (!focusedTask || focusedTask.status === "done") return;
            onCloseTask(focusedTask.id);
          }}
          disabled={!focusedTask || focusedTask.status === "done"}
          title="Закрыть фокусную задачу"
          disabledReason="Недостаточно прав для изменения статуса задачи"
        >
          Закрыть фокусную задачу
        </ActionButton>
        {summaryLink ? (
          <Button size="sm" variant="outline" asChild>
            <Link to={summaryLink}>Открыть summary сущности</Link>
          </Button>
        ) : null}
        {timelineLink ? (
          <Button size="sm" variant="outline" asChild>
            <Link to={timelineLink}>Открыть timeline сущности</Link>
          </Button>
        ) : null}
        {entityContextPath(focusedTask?.entity_type ?? focusedEntityType) ? (
          <Button size="sm" variant="outline" asChild>
            <Link to={contextPath}>Открыть контекст сущности</Link>
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" asChild>
          <Link to="/tasks">Сбросить фокус</Link>
        </Button>
      </div>
    </div>
  );
};

