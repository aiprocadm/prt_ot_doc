import { useEffect } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { TaskTable } from "@/features/tasks/TaskTable";
import { useTasksStore } from "@/stores/tasks";

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

const TasksPage = () => {
  const { list, loading, filters, setFilters } = useTasksStore();

  useEffect(() => {
    list();
  }, [list]);

  const handleTypeChange = (value: string) => {
    setFilters({ type: value || undefined });
    list({ type: value || undefined });
  };

  const handleDueFilterChange = (value: string) => {
    const overdue = value === "overdue" ? true : value === "upcoming" ? false : undefined;
    setFilters({ overdue });
    list({ overdue });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Задачи" }]} />
        <Button variant="outline" onClick={() => list()} disabled={loading}>
          Обновить
        </Button>
      </div>
      <Card>
        <CardContent className="py-6">
          <div className="mb-4 flex flex-wrap gap-4">
            <label className="flex flex-col gap-1 text-sm text-muted-foreground">
              Тип
              <select
                className="rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
                value={filters.type ?? ""}
                onChange={(event) => handleTypeChange(event.target.value)}
              >
                {TASK_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-muted-foreground">
              Срок
              <select
                className="rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
                value={filters.overdue === true ? "overdue" : filters.overdue === false ? "upcoming" : "all"}
                onChange={(event) => handleDueFilterChange(event.target.value)}
              >
                {DUE_FILTER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <TaskTable />
        </CardContent>
      </Card>
    </div>
  );
};

export default TasksPage;
