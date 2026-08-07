import { useState } from "react";
import { toast } from "sonner";

import { approvalsApi, type ApprovalTask } from "@/api/approvals";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Props = {
  task: ApprovalTask;
  onChanged: () => Promise<void> | void;
};

const ApprovalTaskCard = ({ task, onChanged }: Props) => {
  const [comment, setComment] = useState("");
  const [delegateTo, setDelegateTo] = useState("");
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await onChanged();
      toast.success("Решение по задаче сохранено");
    } catch {
      toast.error("Не удалось сохранить решение по задаче");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="font-medium">Задача {task.id.slice(0, 8)}</div>
        <div className="text-xs text-muted-foreground">
          due: {task.due_at ?? "—"}
        </div>
      </div>
      <div className="text-sm text-muted-foreground">
        Процесс: {task.instance_id ?? task.process_id ?? "—"}
      </div>
      <Input
        placeholder="Комментарий"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        <Button
          className="h-12"
          disabled={busy}
          onClick={() =>
            run(() => approvalsApi.decideTask(task.id, "approve", comment))
          }
        >
          Согласовать
        </Button>
        <Button
          className="h-12"
          variant="destructive"
          disabled={busy}
          onClick={() =>
            run(() => approvalsApi.decideTask(task.id, "reject", comment))
          }
        >
          Отклонить
        </Button>
      </div>
      <div className="flex gap-2">
        <Input
          placeholder="ID пользователя для делегирования"
          value={delegateTo}
          onChange={(e) => setDelegateTo(e.target.value)}
        />
        <Button
          disabled={busy || !delegateTo.trim()}
          onClick={() =>
            run(() =>
              approvalsApi.delegateTask(task.id, delegateTo.trim(), comment),
            )
          }
        >
          Делегировать
        </Button>
      </div>
    </div>
  );
};

export default ApprovalTaskCard;
