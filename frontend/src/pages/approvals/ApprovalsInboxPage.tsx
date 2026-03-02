import { useEffect, useState } from "react";

import { approvalsApi, type ApprovalProcess, type ApprovalTask } from "@/api/approvals";
import { edoApi, type EdoEnvelope } from "@/api/edo";
import { signApi, type SignatureRequest } from "@/api/sign";
import ApprovalTaskCard from "@/components/ApprovalTaskCard";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const ApprovalsInboxPage = () => {
  const [tasks, setTasks] = useState<ApprovalTask[]>([]);
  const [doneTasks, setDoneTasks] = useState<ApprovalTask[]>([]);
  const [processes, setProcesses] = useState<ApprovalProcess[]>([]);
  const [edos, setEdos] = useState<EdoEnvelope[]>([]);
  const [signatures, setSignatures] = useState<SignatureRequest[]>([]);

  const load = async () => {
    const [openTasks, closed, list, edoItems, signItems] = await Promise.all([
      approvalsApi.listMyTasks("open"),
      approvalsApi.listMyTasks("done"),
      approvalsApi.listProcesses(),
      edoApi.list(),
      signApi.list(),
    ]);
    setTasks(openTasks);
    setDoneTasks(closed);
    setProcesses(list);
    setEdos(edoItems);
    setSignatures(signItems);
  };

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">ЭДО/Подписи/Согласования</h1>
      <Tabs defaultValue="my-tasks">
        <TabsList>
          <TabsTrigger value="my-tasks">Задачи согласования</TabsTrigger>
          <TabsTrigger value="routes">Маршруты/инстансы</TabsTrigger>
          <TabsTrigger value="signatures">Подписи</TabsTrigger>
          <TabsTrigger value="edo">ЭДО</TabsTrigger>
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
        <TabsContent value="routes" className="space-y-2">
          {processes.map((p) => (
            <div key={p.id} className="rounded border p-3 text-sm">
              <div>#{p.id.slice(0, 8)} — {p.status}</div>
              <div className="text-muted-foreground">object={p.object_id}, step={p.current_step}</div>
            </div>
          ))}
        </TabsContent>
        <TabsContent value="signatures" className="space-y-2">
          {signatures.map((s) => (
            <div key={s.id} className="rounded border p-3 text-sm">
              <div>#{s.id.slice(0, 8)} — {s.status}</div>
              <div className="text-muted-foreground">provider={s.provider}</div>
            </div>
          ))}
        </TabsContent>
        <TabsContent value="edo" className="space-y-2">
          {edos.map((e) => (
            <div key={e.id} className="rounded border p-3 text-sm">
              <div>#{e.id.slice(0, 8)} — {e.status}</div>
              <div className="text-muted-foreground">external_id={e.external_id ?? "—"}</div>
            </div>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ApprovalsInboxPage;
