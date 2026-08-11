export const defaultWorkflowGraph = {
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

export type WorkflowVersion = {
  id: string;
  version_no: number;
  status: string;
  graph_json: { nodes?: Array<{ id: string; type: string; name?: string }>; transitions?: Array<{ from: string; to: string; when?: string }> };
};

export type WorkflowDefinition = {
  id: string;
  code: string;
  name: string;
  entity_type: string;
  versions: WorkflowVersion[];
};

export type WorkflowTask = {
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

export type WorkflowTimelineEvent = {
  id: string;
  node_id?: string | null;
  event_type: string;
  actor_user_id?: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type WorkflowInstanceListItem = {
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

export type WorkflowInstance = {
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

