import { useEffect, useState } from "react";

import { approvalsApi, type ApprovalProcess, type ApprovalTask } from "@/api/approvals";
import ApprovalTaskCard from "@/components/ApprovalTaskCard";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const ApprovalsInboxPage = () => {
  const [tasks, setTasks] = useState<ApprovalTask[]>([]);
  const [doneTasks, setDoneTasks] = useState<ApprovalTask[]>([]);
  const [processes, setProcesses] = useState<ApprovalProcess[]>([]);

  const load = async () => {
    const [openTasks, closed, list] = await Promise.all([
      approvalsApi.listMyTasks("open"),
      approvalsApi.listMyTasks("done"),
      approvalsApi.listProcesses(),
    ]);
    setTasks(openTasks);
    setDoneTasks(closed);
    setProcesses(list);
  };

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">ЭДО/Подписи/Согласования</h1>
      <Tabs defaultValue="my-tasks">
        <TabsList>
          <TabsTrigger value="my-tasks">Мои задачи</TabsTrigger>
          <TabsTrigger value="processes">Процессы</TabsTrigger>
        </TabsList>
        <TabsContent value="my-tasks" className="space-y-3">
          {tasks.map((task) => (
            <ApprovalTaskCard key={task.id} task={task} onChanged={load} />
          ))}
          {tasks.length === 0 && <div className="text-sm text-muted-foreground">Открытых задач нет</div>}
          {doneTasks.length > 0 && (
            <div className="text-sm text-muted-foreground">Выполнено: {doneTasks.length}</div>
          )}
        </TabsContent>
        <TabsContent value="processes" className="space-y-2">
          {processes.map((p) => (
            <div key={p.id} className="rounded border p-3 text-sm">
              <div>#{p.id.slice(0, 8)} — {p.status}</div>
              <div className="text-muted-foreground">object={p.object_id}, step={p.current_step}</div>
            </div>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ApprovalsInboxPage;
