import { useEffect } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { TaskTable } from "@/features/tasks/TaskTable";
import { useTasksStore } from "@/stores/tasks";

const TasksPage = () => {
  const { list, loading } = useTasksStore();

  useEffect(() => {
    list();
  }, [list]);

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
          <TaskTable />
        </CardContent>
      </Card>
    </div>
  );
};

export default TasksPage;
