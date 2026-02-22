import { addDays, endOfDay, isWithinInterval, startOfDay } from "date-fns";
import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FilterField } from "@/components/common/FilterField";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { TaskTable } from "@/features/tasks/TaskTable";
import { useTasksStore } from "@/stores/tasks";
import type { TaskPriority } from "@/types/dto/tasks";

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
  const { list, loading, filters, setFilters, items, pagination } = useTasksStore();
  const [searchParams] = useSearchParams();

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
    setFilters({ type: value || undefined });
    list({ type: value || undefined });
  };

  const handleDueFilterChange = (value: string) => {
    const overdue = value === "overdue" ? true : value === "upcoming" ? false : undefined;
    setFilters({ overdue });
    list({ overdue });
  };

  const handlePriorityChange = (value: string) => {
    const priority = value && isTaskPriority(value) ? value : undefined;
    setFilters({ priority });
    list({ priority });
  };

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Задачи" }]} />
      <RegistryPageHeader
        title="Задачи и обязательства"
        description="Контроль сроков, статусов и исполнителей по обязательствам."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => {
                setFilters({ type: undefined, overdue: undefined });
                list({ type: undefined, overdue: undefined });
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
          <TaskTable />
        </CardContent>
      </Card>
    </div>
  );
};

export default TasksPage;
