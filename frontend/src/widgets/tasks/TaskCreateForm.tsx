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
  linkType: "" | "employee" | "company" | "task";
  linkEntityId: string;
  creating: boolean;
  priorityOptions: Option[];
  isTaskPriority: (value: string) => value is TaskPriority;
  setTitle: (value: string) => void;
  setDescription: (value: string) => void;
  setDueAt: (value: string) => void;
  setPriority: (value: TaskPriority) => void;
  setLinkType: (value: "" | "employee" | "company" | "task") => void;
  setLinkEntityId: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
};

export const TaskCreateForm = ({
  visible,
  title,
  description,
  dueAt,
  priority,
  linkType,
  linkEntityId,
  creating,
  priorityOptions,
  isTaskPriority,
  setTitle,
  setDescription,
  setDueAt,
  setPriority,
  setLinkType,
  setLinkEntityId,
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
        <FilterField label="Привязка" htmlFor="new-task-link-type">
          <select
            id="new-task-link-type"
            className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground"
            value={linkType}
            onChange={(event) =>
              setLinkType(
                event.target.value === "employee" ||
                  event.target.value === "company" ||
                  event.target.value === "task"
                  ? event.target.value
                  : ""
              )
            }
          >
            <option value="">Без привязки</option>
            <option value="employee">К сотруднику</option>
            <option value="company">К организации</option>
            <option value="task">К другой задаче</option>
          </select>
        </FilterField>
        <FilterField label="ID для привязки" htmlFor="new-task-link-id">
          <input
            id="new-task-link-id"
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground"
            value={linkEntityId}
            onChange={(event) => setLinkEntityId(event.target.value)}
            placeholder={
              linkType === "employee"
                ? "ID сотрудника (person)"
                : linkType === "company"
                  ? "ID организации (company)"
                  : linkType === "task"
                    ? "ID задачи"
                    : "Выберите тип привязки"
            }
            disabled={!linkType}
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

