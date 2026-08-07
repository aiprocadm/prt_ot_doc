import { useEffect, useMemo, useState } from "react";

import { workflowApi } from "@/api/workflow";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import {
  defaultWorkflowGraph,
  type WorkflowDefinition,
  type WorkflowInstance,
  type WorkflowInstanceListItem,
  type WorkflowTask,
} from "@/features/workflow/types";
import type { ApiError } from "@/types/dto/common";
import { WorkflowComposerCard } from "@/widgets/workflow/WorkflowComposerCard";
import { WorkflowDefinitionsCard } from "@/widgets/workflow/WorkflowDefinitionsCard";
import { WorkflowRuntimePanel } from "@/widgets/workflow/WorkflowRuntimePanel";

const WorkflowPage = () => {
  const [definitions, setDefinitions] = useState<WorkflowDefinition[]>([]);
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [selectedInstance, setSelectedInstance] =
    useState<WorkflowInstance | null>(null);
  const [instances, setInstances] = useState<WorkflowInstanceListItem[]>([]);
  const [newCode, setNewCode] = useState("document-approval-v1");
  const [graphText, setGraphText] = useState(
    JSON.stringify(defaultWorkflowGraph, null, 2),
  );
  const [validation, setValidation] = useState<string | null>(null);
  const [reassignRole, setReassignRole] = useState("admin");
  const [reassignUserId, setReassignUserId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextDefinitions, nextTasks, nextInstances] = await Promise.all([
        workflowApi.getDefinitions(),
        workflowApi.getTasks(),
        workflowApi.getInstances(),
      ]);
      setDefinitions(nextDefinitions);
      setTasks(nextTasks);
      setInstances(nextInstances);
    } catch (nextError) {
      setError(
        (nextError as ApiError) ?? {
          message: "Не удалось загрузить workflow данные",
        },
      );
    } finally {
      setLoading(false);
    }
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

  const hasOperationalData =
    definitions.length > 0 ||
    tasks.length > 0 ||
    instances.length > 0 ||
    selectedInstance !== null;

  const setActionError = (nextError: unknown, fallbackMessage: string) => {
    setError((nextError as ApiError) ?? { message: fallbackMessage });
  };

  const createProcess = async () => {
    if (!parsedGraph) return;
    setError(null);
    try {
      await workflowApi.createDefinition({
        code: newCode,
        name: "Document approval",
        entity_type: "document",
        description: "Описание процесса на основе JSON-графа",
        graph: parsedGraph,
        variables_schema: {
          approved: "boolean",
          initiator_id: "string",
          escalation_role: "string",
        },
      });
      await load();
    } catch (nextError) {
      setActionError(nextError, "Не удалось создать workflow definition");
    }
  };

  const validateGraph = async () => {
    if (!parsedGraph) {
      setValidation("JSON графа невалиден");
      return;
    }
    try {
      const response = await workflowApi.validateDefinition({
        code: newCode,
        name: "Проверка",
        entity_type: "document",
        graph: parsedGraph,
        variables_schema: {},
      });
      setValidation(
        `Граф валиден · типы узлов: ${(response.node_types ?? []).join(", ")}`,
      );
    } catch (nextError) {
      setValidation(
        (nextError as ApiError)?.message ??
          "Не удалось проверить граф процесса",
      );
    }
  };

  const publish = async (versionId: string) => {
    setError(null);
    try {
      await workflowApi.publishVersion(versionId);
      await load();
    } catch (nextError) {
      setActionError(nextError, "Не удалось опубликовать версию процесса");
    }
  };

  const archive = async (versionId: string) => {
    setError(null);
    try {
      await workflowApi.archiveVersion(versionId);
      await load();
    } catch (nextError) {
      setActionError(nextError, "Не удалось отправить версию в архив");
    }
  };

  const start = async (definitionCode: string) => {
    setError(null);
    try {
      const response = await workflowApi.startInstance(definitionCode);
      setSelectedInstance(response);
      await load();
    } catch (nextError) {
      setActionError(nextError, "Не удалось запустить экземпляр процесса");
    }
  };

  const openInstance = async (instanceId: string) => {
    setError(null);
    try {
      const response = await workflowApi.getInstance(instanceId);
      setSelectedInstance(response);
    } catch (nextError) {
      setActionError(nextError, "Не удалось загрузить экземпляр процесса");
    }
  };

  const completeTask = async (taskId: string) => {
    setError(null);
    try {
      await workflowApi.completeTask(taskId);
      await load();
    } catch (nextError) {
      setActionError(nextError, "Не удалось завершить задачу процесса");
    }
  };

  const moveTask = async (
    taskId: string,
    mode: "delegate" | "escalate" | "reassign",
  ) => {
    setError(null);
    try {
      await workflowApi.moveTask(taskId, mode, reassignRole, reassignUserId);
      await load();
    } catch (nextError) {
      setActionError(
        nextError,
        `Не удалось выполнить действие «${mode}» для задачи процесса`,
      );
    }
  };

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Главная", to: "/dashboard" },
          { label: "Процессы (workflow)" },
        ]}
      />
      <ErrorState error={error ?? undefined} onRetry={() => void load()} />
      {loading ? <LoadingScreen label="Загрузка данных процессов" /> : null}
      {!loading && !error && !hasOperationalData ? (
        <EmptyState
          title="Нет данных по процессам"
          description="Определения, экземпляры и задачи появятся после создания и запуска первого процесса."
        />
      ) : null}
      <WorkflowComposerCard
        newCode={newCode}
        graphText={graphText}
        validation={validation}
        setNewCode={setNewCode}
        setGraphText={setGraphText}
        onValidate={() => void validateGraph()}
        onCreate={() => void createProcess()}
        onRefresh={() => void load()}
      />

      <div className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
        <WorkflowDefinitionsCard
          loading={loading}
          hasError={Boolean(error)}
          definitions={definitions}
          onStart={(code) => void start(code)}
          onPublish={(versionId) => void publish(versionId)}
          onArchive={(versionId) => void archive(versionId)}
        />
        <WorkflowRuntimePanel
          loading={loading}
          hasError={Boolean(error)}
          instances={instances}
          tasks={tasks}
          selectedInstance={selectedInstance}
          reassignRole={reassignRole}
          reassignUserId={reassignUserId}
          setReassignRole={setReassignRole}
          setReassignUserId={setReassignUserId}
          onOpenInstance={(id) => void openInstance(id)}
          onCompleteTask={(id) => void completeTask(id)}
          onMoveTask={(id, mode) => void moveTask(id, mode)}
        />
      </div>
    </div>
  );
};

export default WorkflowPage;
