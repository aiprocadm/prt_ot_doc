import { FilterField } from "@/components/common/FilterField";
import { Button } from "@/components/ui/button";
import type { TaskPriority } from "@/types/dto/tasks";

type Option = { value: string; label: string };

type Props = {
  visible: boolean;
  title: string;
  description: string;
  dueAt: string;
  priority: TaskPriority;
  creating: boolean;
  priorityOptions: Option[];
  isTaskPriority: (value: string) => value is TaskPriority;
  setTitle: (value: string) => void;
  setDescription: (value: string) => void;
  setDueAt: (value: string) => void;
  setPriority: (value: TaskPriority) => void;
  onSubmit: () => void;
  onCancel: () => void;
};

export const TaskCreateForm = ({
  visible,
  title,
  description,
  dueAt,
  priority,
  creating,
  priorityOptions,
  isTaskPriority,
  setTitle,
  setDescription,
  setDueAt,
  setPriority,
  onSubmit,
  onCancel
}: Props) => {
  if (!visible) return null;

  return (
    <div className="mb-4 rounded-md border p-4">
      <div className="mb-3 text-sm font-semibold">Новая задача</div>
      <div className="grid gap-3 md:grid-cols-2">
        <FilterField label="Название" htmlFor="new-task-title">
          <input
            id="new-task-title"
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Например: Проверить комплект документов"
          />
        </FilterField>
        <FilterField label="Срок (опционально)" htmlFor="new-task-due-at">
          <input
            id="new-task-due-at"
            type="datetime-local"
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
            value={dueAt}
            onChange={(event) => setDueAt(event.target.value)}
          />
        </FilterField>
        <FilterField label="Приоритет" htmlFor="new-task-priority">
          <select
            id="new-task-priority"
            className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground"
            value={priority}
            onChange={(event) => setPriority(isTaskPriority(event.target.value) ? event.target.value : "medium")}
          >
            {priorityOptions.filter((option) => option.value).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Описание" htmlFor="new-task-description">
          <input
            id="new-task-description"
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Короткое описание"
          />
        </FilterField>
      </div>
      <div className="mt-3 flex gap-2">
        <Button onClick={onSubmit} disabled={creating}>
          {creating ? "Добавление..." : "Сохранить задачу"}
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={creating}>
          Отмена
        </Button>
      </div>
    </div>
  );
};

