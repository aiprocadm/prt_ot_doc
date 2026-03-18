import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type WorkflowVersion = {
  id: string;
  version_no: number;
  status: string;
  graph_json: { nodes?: Array<{ id: string; type: string; name?: string }>; transitions?: Array<{ from: string; to: string; when?: string }> };
};

type WorkflowDefinition = {
  id: string;
  code: string;
  name: string;
  entity_type: string;
  versions: WorkflowVersion[];
};

type WorkflowTask = {
  id: string;
  title: string;
  instance_id: string;
  node_id: string;
  status: string;
  assignee_user_id?: string | null;
  assignee_role_code?: string | null;
  due_at?: string | null;
};

const DEMO_GRAPH = {
  nodes: [
    { id: "start", type: "start", name: "Старт" },
    { id: "approval", type: "approval", name: "Согласование", sla_hours: 24 },
    { id: "notify", type: "notification", name: "Уведомление" },
    { id: "end", type: "end", name: "Завершение" }
  ],
  transitions: [
    { from: "start", to: "approval" },
    { from: "approval", to: "notify" },
    { from: "notify", to: "end" }
  ]
};

const WorkflowPage = () => {
  const [definitions, setDefinitions] = useState<WorkflowDefinition[]>([]);
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [selectedInstance, setSelectedInstance] = useState<any | null>(null);
  const [newCode, setNewCode] = useState("document-approval-v1");

  const load = async () => {
    const [definitionsResponse, tasksResponse] = await Promise.all([
      apiClient.get<WorkflowDefinition[]>("/workflow/definitions"),
      apiClient.get<WorkflowTask[]>("/workflow/tasks")
    ]);
    setDefinitions(definitionsResponse.data);
    setTasks(tasksResponse.data);
  };

  useEffect(() => {
    void load();
  }, []);

  const createDemo = async () => {
    await apiClient.post("/workflow/definitions", {
      code: newCode,
      name: "Document approval",
      entity_type: "document",
      description: "Demo JSON-driven workflow",
      graph: DEMO_GRAPH,
      variables_schema: { amount: "number", initiator_id: "string" }
    });
    await load();
  };

  const publish = async (versionId: string) => {
    await apiClient.post(`/workflow/versions/${versionId}/publish`);
    await load();
  };

  const start = async (definitionCode: string) => {
    const response = await apiClient.post("/workflow/instances", {
      definition_code: definitionCode,
      entity_type: "document",
      entity_id: `doc-${Date.now()}`,
      context: { approved: true, initiator_id: "current-user" }
    });
    setSelectedInstance(response.data);
    await load();
  };

  const openInstance = async (instanceId: string) => {
    const response = await apiClient.get(`/workflow/instances/${instanceId}`);
    setSelectedInstance(response.data);
  };

  const completeTask = async (taskId: string) => {
    await apiClient.post(`/workflow/tasks/${taskId}/complete`, { decision: "approve", payload: { approved: true } });
    await load();
  };

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Workflow" }]} />
      <Card>
        <CardHeader>
          <CardTitle>Workflow / BPM engine v1</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="w-full max-w-md space-y-2">
            <label className="text-sm font-medium">Код процесса</label>
            <Input value={newCode} onChange={(event) => setNewCode(event.target.value)} />
          </div>
          <Button onClick={() => void createDemo()}>Создать demo process</Button>
          <Button variant="outline" onClick={() => void load()}>Обновить</Button>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.4fr,1fr]">
        <Card>
          <CardHeader><CardTitle>Процессы</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {definitions.map((definition) => (
              <div key={definition.id} className="rounded-lg border p-4 space-y-3">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="font-medium">{definition.name}</div>
                    <div className="text-sm text-muted-foreground">{definition.code} · entity: {definition.entity_type}</div>
                  </div>
                  <Button size="sm" onClick={() => void start(definition.code)}>Запустить</Button>
                </div>
                {definition.versions.map((version) => (
                  <div key={version.id} className="rounded border bg-muted/30 p-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-medium">Версия {version.version_no}</div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs uppercase text-muted-foreground">{version.status}</span>
                        {version.status !== "published" ? <Button size="sm" variant="outline" onClick={() => void publish(version.id)}>Publish</Button> : null}
                      </div>
                    </div>
                    <div className="mt-3 grid gap-2 md:grid-cols-2">
                      <div>
                        <div className="text-xs font-medium uppercase text-muted-foreground">Узлы</div>
                        <ul className="mt-1 text-sm space-y-1">
                          {(version.graph_json.nodes ?? []).map((node) => <li key={node.id}>{node.id} · {node.type} · {node.name ?? "—"}</li>)}
                        </ul>
                      </div>
                      <div>
                        <div className="text-xs font-medium uppercase text-muted-foreground">Переходы</div>
                        <ul className="mt-1 text-sm space-y-1">
                          {(version.graph_json.transitions ?? []).map((item, index) => <li key={`${item.from}-${item.to}-${index}`}>{item.from} → {item.to}{item.when ? ` (${item.when})` : ""}</li>)}
                        </ul>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Workflow tasks</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {tasks.map((task) => (
                <div key={task.id} className="rounded border p-3">
                  <div className="font-medium">{task.title}</div>
                  <div className="text-sm text-muted-foreground">{task.node_id} · {task.status}</div>
                  <div className="mt-1 text-xs text-muted-foreground">Assignee: {task.assignee_user_id ?? task.assignee_role_code ?? "unassigned"}</div>
                  <div className="mt-3 flex gap-2">
                    <Button size="sm" onClick={() => void completeTask(task.id)}>Complete</Button>
                    <Button size="sm" variant="outline" onClick={() => void openInstance(task.instance_id)}>Timeline</Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Instance timeline</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {selectedInstance ? (
                <>
                  <div className="text-sm">Entity: {selectedInstance.entity_type} / {selectedInstance.entity_id}</div>
                  <div className="text-sm">Status: {selectedInstance.status}</div>
                  {(selectedInstance.timeline ?? []).map((event: any) => (
                    <div key={event.id} className="rounded border-l-2 border-primary pl-3 py-2">
                      <div className="text-sm font-medium">{event.event_type}</div>
                      <div className="text-xs text-muted-foreground">{event.node_id ?? "system"} · {new Date(event.created_at).toLocaleString()}</div>
                    </div>
                  ))}
                </>
              ) : <div className="text-sm text-muted-foreground">Выберите инстанс или запустите процесс.</div>}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default WorkflowPage;
