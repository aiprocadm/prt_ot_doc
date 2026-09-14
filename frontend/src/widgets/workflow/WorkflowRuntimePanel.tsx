import { statusLabel } from "@/components/common/StatusBadge";
import { Can } from "@/components/permissions/Can";
import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PERMISSIONS } from "@/permissions/permissions";
import type {
  WorkflowInstance,
  WorkflowInstanceListItem,
  WorkflowTask,
} from "@/features/workflow/types";

type Props = {
  loading: boolean;
  hasError: boolean;
  instances: WorkflowInstanceListItem[];
  tasks: WorkflowTask[];
  selectedInstance: WorkflowInstance | null;
  reassignRole: string;
  reassignUserId: string;
  setReassignRole: (value: string) => void;
  setReassignUserId: (value: string) => void;
  onOpenInstance: (id: string) => void;
  onCompleteTask: (id: string) => void;
  onMoveTask: (id: string, mode: "delegate" | "escalate" | "reassign") => void;
};

export const WorkflowRuntimePanel = ({
  loading,
  hasError,
  instances,
  tasks,
  selectedInstance,
  reassignRole,
  reassignUserId,
  setReassignRole,
  setReassignUserId,
  onOpenInstance,
  onCompleteTask,
  onMoveTask,
}: Props) => (
  <div className="space-y-6">
    <Card>
      <CardHeader>
        <CardTitle>Экземпляры процессов</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!loading && !hasError && instances.length === 0 ? (
          <EmptyState
            title="Нет экземпляров процессов"
            description="После запуска здесь появятся активные и завершённые экземпляры."
          />
        ) : null}
        {instances.map((instance) => (
          <div key={instance.id} className="rounded border p-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="font-medium">
                  {instance.entity_type} · {instance.entity_id}
                </div>
                <div className="text-xs text-muted-foreground">
                  узел: {instance.current_node_id ?? "—"} · задач:{" "}
                  {instance.open_tasks} · статус: {statusLabel(instance.status)}
                </div>
                <div className="text-xs text-muted-foreground">
                  корреляция: {instance.correlation_id ?? "—"}
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onOpenInstance(instance.id)}
              >
                Открыть
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle>Задачи процесса</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 md:grid-cols-2">
          <Input
            placeholder="ID пользователя для переназначения"
            value={reassignUserId}
            onChange={(event) => setReassignUserId(event.target.value)}
          />
          <Input
            placeholder="Код роли"
            value={reassignRole}
            onChange={(event) => setReassignRole(event.target.value)}
          />
        </div>
        {!loading && !hasError && tasks.length === 0 ? (
          <EmptyState
            title="Нет задач процесса"
            description="Когда процесс дойдёт до узлов-задач, здесь появятся активные поручения."
          />
        ) : null}
        {tasks.map((task) => (
          <div key={task.id} className="rounded border p-3">
            <div className="font-medium">{task.title}</div>
            <div className="text-sm text-muted-foreground">
              {task.node_id} · {statusLabel(task.status)}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Исполнитель:{" "}
              {task.assignee_user_id ??
                task.assignee_role_code ??
                "не назначен"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Срок (SLA):{" "}
              {task.due_at ? new Date(task.due_at).toLocaleString() : "—"}
            </div>
            {task.task_payload ? (
              <div className="mt-1 text-xs text-muted-foreground">
                Данные: {JSON.stringify(task.task_payload)}
              </div>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              <Can permission={PERMISSIONS.WORKFLOW_MANAGE}>
                {/* Кнопка в повторяющейся строке задачи — вторичная
                    (UX-бюджет: primary на экране одна, у композера). */}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onCompleteTask(task.id)}
                >
                  Завершить
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onMoveTask(task.id, "reassign")}
                >
                  Переназначить
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onMoveTask(task.id, "delegate")}
                >
                  Делегировать
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onMoveTask(task.id, "escalate")}
                >
                  Эскалировать
                </Button>
              </Can>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onOpenInstance(task.instance_id)}
              >
                Хронология
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle>Хронология экземпляра</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {selectedInstance ? (
          <>
            <div className="text-sm">
              Сущность: {selectedInstance.entity_type} /{" "}
              {selectedInstance.entity_id}
            </div>
            <div className="text-sm">
              Статус: {statusLabel(selectedInstance.status)}
            </div>
            <div className="text-sm">
              Корреляция: {selectedInstance.correlation_id ?? "—"}
            </div>
            <div className="rounded border bg-muted/30 p-3 text-xs">
              Контекст:{" "}
              {JSON.stringify(selectedInstance.context_json ?? {}, null, 2)}
            </div>
            {selectedInstance.current_node_id ? (
              <div className="rounded border bg-muted/30 p-3 text-sm">
                Текущий узел:{" "}
                <span className="font-medium">
                  {selectedInstance.current_node_id}
                </span>
              </div>
            ) : null}
            {(selectedInstance.timeline ?? []).map((event) => (
              <div
                key={event.id}
                className="rounded border-l-2 border-primary pl-3 py-2"
              >
                <div className="text-sm font-medium">{event.event_type}</div>
                <div className="text-xs text-muted-foreground">
                  {event.node_id ?? "система"} ·{" "}
                  {new Date(event.created_at).toLocaleString()}
                </div>
                {Object.keys(event.payload ?? {}).length ? (
                  <div className="text-xs text-muted-foreground">
                    {JSON.stringify(event.payload)}
                  </div>
                ) : null}
              </div>
            ))}
          </>
        ) : (
          <div className="text-sm text-muted-foreground">
            Выберите инстанс или запустите процесс.
          </div>
        )}
      </CardContent>
    </Card>
  </div>
);
