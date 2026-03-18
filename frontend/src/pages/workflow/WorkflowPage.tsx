import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const defaultGraph = {
  nodes: [
    { id: "start", type: "start", name: "Старт" },
    { id: "approval", type: "approval", name: "Согласование", sla_hours: 24, assignee_role_code: "line_manager" },
    { id: "notify", type: "notification", name: "Уведомление", destination: "inapp" },
    { id: "end", type: "end", name: "Завершение" }
  ],
  transitions: [
    { from: "start", to: "approval" },
    { from: "approval", to: "notify" },
    { from: "notify", to: "end" }
  ]
};

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
  task_payload?: Record<string, unknown>;
};

type WorkflowTimelineEvent = {
  id: string;
  node_id?: string | null;
  event_type: string;
  actor_user_id?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

type WorkflowInstanceListItem = {
  id: string;
  definition_id: string;
  definition_version_id: string;
  entity_type: string;
  entity_id: string;
  status: string;
  current_node_id?: string | null;
  correlation_id?: string | null;
  open_tasks: number;
  updated_at: string;
};

type WorkflowInstance = {
  id: string;
  definition_id: string;
  definition_version_id: string;
  entity_type: string;
  entity_id: string;
  status: string;
  current_node_id?: string | null;
  context_json: Record<string, unknown>;
  correlation_id?: string | null;
  timeline: WorkflowTimelineEvent[];
  tasks: WorkflowTask[];
};

const WorkflowPage = () => {
  const [definitions, setDefinitions] = useState<WorkflowDefinition[]>([]);
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [selectedInstance, setSelectedInstance] = useState<WorkflowInstance | null>(null);
  const [instances, setInstances] = useState<WorkflowInstanceListItem[]>([]);
  const [newCode, setNewCode] = useState("document-approval-v1");
  const [graphText, setGraphText] = useState(JSON.stringify(defaultGraph, null, 2));
  const [validation, setValidation] = useState<string | null>(null);
  const [reassignRole, setReassignRole] = useState("admin");
  const [reassignUserId, setReassignUserId] = useState("");

  const load = async () => {
    const [definitionsResponse, tasksResponse, instancesResponse] = await Promise.all([
      apiClient.get<WorkflowDefinition[]>("/workflow/definitions"),
      apiClient.get<WorkflowTask[]>("/workflow/tasks"),
      apiClient.get<WorkflowInstanceListItem[]>("/workflow/instances")
    ]);
    setDefinitions(definitionsResponse.data);
    setTasks(tasksResponse.data);
    setInstances(instancesResponse.data);
  };

  useEffect(() => {
    void load();
  }, []);

  const parsedGraph = useMemo(() => {
    try {
      return JSON.parse(graphText);
    } catch {
      return null;
    }
  }, [graphText]);

  const createProcess = async () => {
    if (!parsedGraph) return;
    await apiClient.post("/workflow/definitions", {
      code: newCode,
      name: "Document approval",
      entity_type: "document",
      description: "JSON-driven workflow definition",
      graph: parsedGraph,
      variables_schema: { approved: "boolean", initiator_id: "string", escalation_role: "string" }
    });
    await load();
  };

  const validateGraph = async () => {
    if (!parsedGraph) {
      setValidation("JSON графа невалиден");
      return;
    }
    const response = await apiClient.post("/workflow/definitions/validate", {
      code: newCode,
      name: "Validation",
      entity_type: "document",
      graph: parsedGraph,
      variables_schema: {}
    });
    setValidation(`OK · узлы: ${(response.data.node_types ?? []).join(", ")}`);
  };

  const publish = async (versionId: string) => {
    await apiClient.post(`/workflow/versions/${versionId}/publish`);
    await load();
  };

  const archive = async (versionId: string) => {
    await apiClient.post(`/workflow/versions/${versionId}/archive`);
    await load();
  };

  const start = async (definitionCode: string) => {
    const response = await apiClient.post<WorkflowInstance>("/workflow/instances", {
      definition_code: definitionCode,
      entity_type: "document",
      entity_id: `doc-${Date.now()}`,
      context: { approved: true, initiator_id: "current-user", escalation_role: "safety_admin" }
    });
    setSelectedInstance(response.data);
    await load();
  };

  const openInstance = async (instanceId: string) => {
    const response = await apiClient.get<WorkflowInstance>(`/workflow/instances/${instanceId}`);
    setSelectedInstance(response.data);
  };

  const completeTask = async (taskId: string) => {
    await apiClient.post(`/workflow/tasks/${taskId}/complete`, { decision: "approve", payload: { approved: true } });
    await load();
  };

  const moveTask = async (taskId: string, mode: "delegate" | "escalate" | "reassign") => {
    await apiClient.post(`/workflow/tasks/${taskId}/${mode}`, {
      ...(reassignUserId ? { assignee_user_id: reassignUserId } : {}),
      assignee_role_code: reassignRole || undefined
    });
    await load();
  };

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Главная", to: "/dashboard" }, { label: "Workflow" }]} />
      <Card>
        <CardHeader><CardTitle>Workflow / BPM engine v1</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 xl:grid-cols-[0.5fr,1fr]">
            <Input value={newCode} onChange={(event) => setNewCode(event.target.value)} placeholder="Код процесса" />
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void validateGraph()}>Validate graph</Button>
              <Button onClick={() => void createProcess()}>Create draft</Button>
              <Button variant="outline" onClick={() => void load()}>Refresh</Button>
            </div>
          </div>
          <Textarea value={graphText} onChange={(event) => setGraphText(event.target.value)} rows={14} />
          {validation ? <div className="text-sm text-muted-foreground">{validation}</div> : null}
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
        <Card>
          <CardHeader><CardTitle>Процессы и версии</CardTitle></CardHeader>
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
                        {version.status !== "archived" ? <Button size="sm" variant="ghost" onClick={() => void archive(version.id)}>Archive</Button> : null}
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
            <CardHeader><CardTitle>Workflow instances</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {instances.map((instance) => (
                <div key={instance.id} className="rounded border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="font-medium">{instance.entity_type} · {instance.entity_id}</div>
                      <div className="text-xs text-muted-foreground">node: {instance.current_node_id ?? "—"} · tasks: {instance.open_tasks} · status: {instance.status}</div>
                      <div className="text-xs text-muted-foreground">correlation: {instance.correlation_id ?? "—"}</div>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => void openInstance(instance.id)}>Open</Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Workflow tasks</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 md:grid-cols-2">
                <Input placeholder="Reassign user id" value={reassignUserId} onChange={(event) => setReassignUserId(event.target.value)} />
                <Input placeholder="Role code" value={reassignRole} onChange={(event) => setReassignRole(event.target.value)} />
              </div>
              {tasks.map((task) => (
                <div key={task.id} className="rounded border p-3">
                  <div className="font-medium">{task.title}</div>
                  <div className="text-sm text-muted-foreground">{task.node_id} · {task.status}</div>
                  <div className="mt-1 text-xs text-muted-foreground">Assignee: {task.assignee_user_id ?? task.assignee_role_code ?? "unassigned"}</div>
                  <div className="mt-1 text-xs text-muted-foreground">SLA: {task.due_at ? new Date(task.due_at).toLocaleString() : "—"}</div>
                  {task.task_payload ? <div className="mt-1 text-xs text-muted-foreground">Payload: {JSON.stringify(task.task_payload)}</div> : null}
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => void completeTask(task.id)}>Complete</Button>
                    <Button size="sm" variant="outline" onClick={() => void moveTask(task.id, "reassign")}>Reassign</Button>
                    <Button size="sm" variant="outline" onClick={() => void moveTask(task.id, "delegate")}>Delegate</Button>
                    <Button size="sm" variant="outline" onClick={() => void moveTask(task.id, "escalate")}>Escalate</Button>
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
                  <div className="text-sm">Correlation: {selectedInstance.correlation_id ?? "—"}</div>
                  <div className="rounded border bg-muted/30 p-3 text-xs">Context: {JSON.stringify(selectedInstance.context_json ?? {}, null, 2)}</div>
                  {selectedInstance.current_node_id ? <div className="rounded border bg-muted/30 p-3 text-sm">Current node: <span className="font-medium">{selectedInstance.current_node_id}</span></div> : null}
                  {(selectedInstance.timeline ?? []).map((event) => (
                    <div key={event.id} className="rounded border-l-2 border-primary pl-3 py-2">
                      <div className="text-sm font-medium">{event.event_type}</div>
                      <div className="text-xs text-muted-foreground">{event.node_id ?? "system"} · {new Date(event.created_at).toLocaleString()}</div>
                      {Object.keys(event.payload ?? {}).length ? <div className="text-xs text-muted-foreground">{JSON.stringify(event.payload)}</div> : null}
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
