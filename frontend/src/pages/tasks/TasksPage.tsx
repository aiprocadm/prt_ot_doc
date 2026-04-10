import { addDays, endOfDay, isWithinInterval, startOfDay } from "date-fns";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FilterField } from "@/components/common/FilterField";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { ActionButton } from "@/components/permissions/ActionButton";
import { TaskTable } from "@/features/tasks/TaskTable";
import { PERMISSIONS } from "@/permissions/permissions";
import { useTasksStore } from "@/stores/tasks";
import type { TaskPriority } from "@/types/dto/tasks";
import { TaskFocusCard } from "@/widgets/tasks/TaskFocusCard";
import { TaskCreateForm } from "@/widgets/tasks/TaskCreateForm";

const TASK_TYPE_OPTIONS = [
  { value: "", label: "Все типы" },
  { value: "training_plan", label: "Обучение" },
  { value: "medical_requirement", label: "Медосмотры" },
  { value: "inspection", label: "Инспекции" },
  { value: "attestation", label: "Аттестации" }
];

const DUE_FILTER_OPTIONS = [
  { value: "all", label: "Все задачи" },
  { value: "upcoming", label: "Предстоящие" },
  { value: "overdue", label: "Просроченные" }
];

const PRIORITY_OPTIONS = [
  { value: "", label: "Все приоритеты" },
  { value: "low", label: "Низкий" },
  { value: "medium", label: "Средний" },
  { value: "high", label: "Высокий" },
  { value: "critical", label: "Критичный" }
];

const TASK_PRIORITIES: TaskPriority[] = ["low", "medium", "high", "critical"];

const isTaskPriority = (value: string): value is TaskPriority => TASK_PRIORITIES.includes(value as TaskPriority);

const TasksPage = () => {
  const {
    list,
    loading,
    error,
    filters,
    setFilters,
    items,
    item,
    getById,
    patchTask,
    createTask,
    pagination,
    taskFocusLoadError,
    clearTaskFocusState
  } = useTasksStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const updateFilterQuery = (patch: { type?: string; overdue?: boolean; priority?: string }) => {
    const next = new URLSearchParams(searchParams);
    if ("type" in patch) {
      if (patch.type) next.set("type", patch.type);
      else next.delete("type");
    }
    if ("overdue" in patch) {
      if (patch.overdue === undefined) next.delete("overdue");
      else next.set("overdue", String(patch.overdue));
    }
    if ("priority" in patch) {
      if (patch.priority) next.set("priority", patch.priority);
      else next.delete("priority");
    }
    setSearchParams(next, { replace: true });
  };

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskDescription, setNewTaskDescription] = useState("");
  const [newTaskPriority, setNewTaskPriority] = useState<TaskPriority>("medium");
  const [newTaskDueAt, setNewTaskDueAt] = useState("");
  const focusedTaskId = searchParams.get("task_id") ?? undefined;
  const focusedEntityType = searchParams.get("entity_type") ?? undefined;
  const focusedEntityId = searchParams.get("entity_id") ?? undefined;

  useEffect(() => {
    const type = searchParams.get("type") ?? undefined;
    const overdueParam = searchParams.get("overdue");
    const overdue =
      overdueParam === "true" ? true : overdueParam === "false" ? false : undefined;
    const priorityParam = searchParams.get("priority");
    const priority = priorityParam && isTaskPriority(priorityParam) ? priorityParam : undefined;
    setFilters({ type, overdue, priority });
    list({ type, overdue, priority });
  }, [list, searchParams, setFilters]);

  useEffect(() => {
    if (!focusedTaskId) {
      clearTaskFocusState();
      return;
    }
    void getById(focusedTaskId);
  }, [focusedTaskId, getById, clearTaskFocusState]);

  const focusedTask = useMemo(() => {
    if (!focusedTaskId) return null;
    return items.find((task) => task.id === focusedTaskId) ?? (item?.id === focusedTaskId ? item : null);
  }, [focusedTaskId, item, items]);

  const stats = useMemo(() => {
    const now = new Date();
    const todayStart = startOfDay(now);
    const todayEnd = endOfDay(now);
    const weekEnd = endOfDay(addDays(now, 7));

    let overdueCount = 0;
    let todayCount = 0;
    let weekCount = 0;

    items.forEach((task) => {
      if (!task.due_at) return;
      const dueAt = new Date(task.due_at);
      if (task.overdue) overdueCount += 1;
      if (isWithinInterval(dueAt, { start: todayStart, end: todayEnd })) todayCount += 1;
      if (isWithinInterval(dueAt, { start: todayStart, end: weekEnd })) weekCount += 1;
    });

    return { overdueCount, todayCount, weekCount };
  }, [items]);

  const handleTypeChange = (value: string) => {
    const type = value || undefined;
    setFilters({ type });
    list({ type });
    updateFilterQuery({ type });
  };

  const handleDueFilterChange = (value: string) => {
    const overdue = value === "overdue" ? true : value === "upcoming" ? false : undefined;
    setFilters({ overdue });
    list({ overdue });
    updateFilterQuery({ overdue });
  };

  const handlePriorityChange = (value: string) => {
    const priority = value && isTaskPriority(value) ? value : undefined;
    setFilters({ priority });
    list({ priority });
    updateFilterQuery({ priority });
  };

  const resetCreateForm = () => {
    setNewTaskTitle("");
    setNewTaskDescription("");
    setNewTaskPriority("medium");
    setNewTaskDueAt("");
  };

  const handleCreateTask = async () => {
    const title = newTaskTitle.trim();
    if (!title) {
      toast.error("Введите название задачи");
      return;
    }
    setCreating(true);
    const dueAtIso = newTaskDueAt ? new Date(newTaskDueAt).toISOString() : null;
    const created = await createTask({
      title,
      description: newTaskDescription.trim() || null,
      priority: newTaskPriority,
      due_at: dueAtIso
    });
    setCreating(false);
    if (!created) {
      toast.error("Не удалось добавить задачу");
      return;
    }
    toast.success("Задача добавлена");
    resetCreateForm();
    setShowCreateForm(false);
    const next = new URLSearchParams(searchParams);
    next.set("task_id", created.id);
    setSearchParams(next, { replace: true });
    void list();
  };

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Задачи" }]} />
      <RegistryPageHeader
        title="Задачи и обязательства"
        description="Контроль сроков, статусов и исполнителей по обязательствам."
        actions={
          <>
            <ActionButton
              permission={PERMISSIONS.TASK_UPDATE}
              onClick={() => {
                if (showCreateForm) {
                  setShowCreateForm(false);
                  resetCreateForm();
                  return;
                }
                setShowCreateForm(true);
              }}
              title={showCreateForm ? "Скрыть форму добавления задачи" : "Добавить задачу"}
              disabledReason="Недостаточно прав для добавления задачи"
            >
              {showCreateForm ? "Скрыть форму" : "Добавить задачу"}
            </ActionButton>
            <Button
              variant="outline"
              onClick={() => {
                setFilters({ type: undefined, overdue: undefined });
                list({ type: undefined, overdue: undefined });
                updateFilterQuery({ type: undefined, overdue: undefined, priority: undefined });
              }}
              disabled={loading}
            >
              Сбросить фильтры
            </Button>
            <Button variant="default" onClick={() => list()} disabled={loading}>
              Обновить
            </Button>
          </>
        }
        stats={[
          { label: "Всего задач", value: pagination.total },
          { label: "Просрочено (на странице)", value: stats.overdueCount },
          { label: "Сегодня (на странице)", value: stats.todayCount },
          { label: "На 7 дней (на странице)", value: stats.weekCount }
        ]}
      />
      <Card>
        <CardContent className="py-6">
          {focusedTaskId ? (
            <TaskFocusCard
              focusedTaskId={focusedTaskId}
              focusedTask={focusedTask}
              focusLoadError={taskFocusLoadError}
              focusedEntityType={focusedEntityType}
              focusedEntityId={focusedEntityId}
              onCloseTask={(taskId) => {
                void patchTask(taskId, { status: "done" });
              }}
            />
          ) : null}

          <div className="mb-4 flex flex-wrap gap-4">
            <FilterField label="Тип" htmlFor="task-type">
              <select
                id="task-type"
                className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground"
                value={filters.type ?? ""}
                onChange={(event) => handleTypeChange(event.target.value)}
              >
                {TASK_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Срок" htmlFor="task-due">
              <select
                id="task-due"
                className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground"
                value={filters.overdue === true ? "overdue" : filters.overdue === false ? "upcoming" : "all"}
                onChange={(event) => handleDueFilterChange(event.target.value)}
              >
                {DUE_FILTER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Приоритет" htmlFor="task-priority">
              <select
                id="task-priority"
                className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground"
                value={filters.priority ?? ""}
                onChange={(event) => handlePriorityChange(event.target.value)}
              >
                {PRIORITY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FilterField>
          </div>
          <TaskCreateForm
            visible={showCreateForm}
            title={newTaskTitle}
            description={newTaskDescription}
            dueAt={newTaskDueAt}
            priority={newTaskPriority}
            creating={creating}
            priorityOptions={PRIORITY_OPTIONS}
            isTaskPriority={isTaskPriority}
            setTitle={setNewTaskTitle}
            setDescription={setNewTaskDescription}
            setDueAt={setNewTaskDueAt}
            setPriority={setNewTaskPriority}
            onSubmit={() => void handleCreateTask()}
            onCancel={() => {
              setShowCreateForm(false);
              resetCreateForm();
            }}
          />
          <TaskTable />
          <ErrorState error={error ?? undefined} onRetry={() => void list()} />
          {loading && items.length === 0 ? <LoadingScreen label="Загрузка задач" /> : null}
          {!loading && !error && items.length === 0 ? <EmptyState title="Задач нет" description="Измените фильтры или дождитесь появления новых обязательств." /> : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default TasksPage;
