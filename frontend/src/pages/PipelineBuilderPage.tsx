import { useEffect, useMemo, useState } from "react";

import { pipelineBuilderApi } from "@/api/pipelines";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import type { ApiError } from "@/types/dto/common";

type GraphNode = { id: string; type: string; config?: Record<string, unknown> };
type GraphEdge = { from: string; to: string; condition?: string };
type PipelineProfile = {
  id: string;
  code: string;
  name: string;
  profile_version: number;
  graph?: { nodes: GraphNode[]; edges: GraphEdge[] };
};

const NODE_TYPES = [
  "render_docx",
  "apply_headers",
  "replace_dry_run",
  "replace_apply",
  "convert_pdf",
  "build_zip",
  "send_edo",
  "verify_signature",
  "notify",
  "webhook",
  "delay",
  "branch",
  "archive",
  "noop",
] as const;

const defaultGraph: { nodes: GraphNode[]; edges: GraphEdge[] } = {
  nodes: [
    { id: "render", type: "render_docx", config: { template_code: "default" } },
    { id: "headers", type: "apply_headers" },
    { id: "replace", type: "replace_apply" },
    { id: "pdf", type: "convert_pdf" },
  ],
  edges: [
    { from: "render", to: "headers" },
    { from: "headers", to: "replace" },
    { from: "replace", to: "pdf" },
  ],
};

const PipelineBuilderPage = () => {
  const [profiles, setProfiles] = useState<PipelineProfile[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [profilesError, setProfilesError] = useState<ApiError | null>(null);
  const [code, setCode] = useState("doc-default");
  const [name, setName] = useState("Профиль по умолчанию");
  const [graph, setGraph] = useState<{
    nodes: GraphNode[];
    edges: GraphEdge[];
  }>(defaultGraph);
  // BIZ-59: раньше КАЖДОЕ ребро несло три поля прямо в списке — лимит полей
  // зависел от данных (ловушка BillingPage). Теперь редактор один: свойства
  // ВЫБРАННОГО — узла или ребра; списки только выбирают.
  const [selection, setSelection] = useState<
    { kind: "node"; id: string } | { kind: "edge"; idx: number } | null
  >(defaultGraph.nodes[0] ? { kind: "node", id: defaultGraph.nodes[0].id } : null);
  const selectedNodeId = selection?.kind === "node" ? selection.id : "";
  const [configText, setConfigText] = useState(
    JSON.stringify(defaultGraph.nodes[0]?.config ?? {}, null, 2),
  );
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setProfilesLoading(true);
    setProfilesError(null);
    try {
      const response = await pipelineBuilderApi.getProfiles<PipelineProfile>();
      setProfiles(response);
    } catch (loadError) {
      setProfiles([]);
      setProfilesError(loadError as ApiError);
    } finally {
      setProfilesLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const parsedGraph = graph;

  const validationError = useMemo(() => {
    const ids = parsedGraph.nodes.map((n) => n.id);
    if (new Set(ids).size !== ids.length) return "Есть дубли id нод";
    const idSet = new Set(ids);
    const badEdge = parsedGraph.edges.find(
      (e) => !idSet.has(e.from) || !idSet.has(e.to),
    );
    if (badEdge)
      return `Ребро ${badEdge.from} → ${badEdge.to} ссылается на неизвестную ноду`;
    return null;
  }, [parsedGraph]);

  const selectedNode = useMemo(
    () => parsedGraph.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [parsedGraph.nodes, selectedNodeId],
  );

  const selectedEdge =
    selection?.kind === "edge"
      ? (parsedGraph.edges[selection.idx] ?? null)
      : null;

  useEffect(() => {
    setConfigText(JSON.stringify(selectedNode?.config ?? {}, null, 2));
  }, [selectedNode]);

  const addNode = () => {
    const nextIdx = parsedGraph.nodes.length + 1;
    const node: GraphNode = { id: `node_${nextIdx}`, type: "noop", config: {} };
    setGraph((prev) => ({ ...prev, nodes: [...prev.nodes, node] }));
    setSelection({ kind: "node", id: node.id });
  };

  const addEdge = () => {
    if (parsedGraph.nodes.length < 2) return;
    const fallbackFrom =
      parsedGraph.nodes[parsedGraph.nodes.length - 2]?.id ??
      parsedGraph.nodes[0].id;
    const fallbackTo =
      parsedGraph.nodes[parsedGraph.nodes.length - 1]?.id ??
      parsedGraph.nodes[0].id;
    const nextIdx = parsedGraph.edges.length;
    setGraph((prev) => ({
      ...prev,
      edges: [...prev.edges, { from: fallbackFrom, to: fallbackTo }],
    }));
    setSelection({ kind: "edge", idx: nextIdx });
  };

  const updateNode = (nodeId: string, patch: Partial<GraphNode>) => {
    setGraph((prev) => {
      const nextNodes = prev.nodes.map((node) =>
        node.id === nodeId ? { ...node, ...patch } : node,
      );
      const nextNodeId = patch.id ?? nodeId;
      const nextEdges =
        patch.id && patch.id !== nodeId
          ? prev.edges.map((edge) => ({
              ...edge,
              from: edge.from === nodeId ? nextNodeId : edge.from,
              to: edge.to === nodeId ? nextNodeId : edge.to,
            }))
          : prev.edges;
      return { ...prev, nodes: nextNodes, edges: nextEdges };
    });
    if (patch.id) {
      setSelection({ kind: "node", id: patch.id });
    }
  };

  const removeNode = (nodeId: string) => {
    setGraph((prev) => ({
      nodes: prev.nodes.filter((n) => n.id !== nodeId),
      edges: prev.edges.filter((e) => e.from !== nodeId && e.to !== nodeId),
    }));
    // Вместе с узлом уходят его рёбра — индексы сдвигаются, выбор сбрасываем.
    setSelection(null);
  };

  const updateEdge = (idx: number, patch: Partial<GraphEdge>) => {
    setGraph((prev) => ({
      ...prev,
      edges: prev.edges.map((edge, edgeIdx) =>
        edgeIdx === idx ? { ...edge, ...patch } : edge,
      ),
    }));
  };

  const removeEdge = (idx: number) => {
    setGraph((prev) => ({
      ...prev,
      edges: prev.edges.filter((_, edgeIdx) => edgeIdx !== idx),
    }));
    setSelection(null);
  };

  const save = async () => {
    try {
      setError(null);
      if (validationError) throw new Error(validationError);
      await pipelineBuilderApi.createProfile({
        code,
        name,
        graph: parsedGraph,
        is_active: true,
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка сохранения");
    }
  };

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">
        Конструктор процессов (low-code)
      </h1>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2 rounded border p-3 text-sm">
          <input
            className="w-full rounded border px-2 py-1"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Код профиля"
          />
          <input
            className="w-full rounded border px-2 py-1"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Название"
          />
          <div className="space-y-2 rounded border p-2">
            <div className="flex flex-wrap gap-2">
              <button className="rounded border px-2 py-1" onClick={addNode}>
                + Нода
              </button>
              <button className="rounded border px-2 py-1" onClick={addEdge}>
                + Ребро
              </button>
            </div>
            <div className="grid gap-3 lg:grid-cols-[1.3fr_1fr]">
              <div className="space-y-2">
                <div className="text-xs font-medium text-muted-foreground">
                  Холст (узлы и связи)
                </div>
                <div className="max-h-52 space-y-2 overflow-auto rounded border p-2">
                  {parsedGraph.nodes.map((node, nodeIdx) => (
                    <button
                      key={`${node.id}-${nodeIdx}`}
                      type="button"
                      className={`w-full rounded border p-2 text-left text-xs ${selectedNodeId === node.id ? "border-blue-500 bg-blue-50" : ""}`}
                      onClick={() => setSelection({ kind: "node", id: node.id })}
                    >
                      <div className="font-medium">{node.id}</div>
                      <div className="text-muted-foreground">{node.type}</div>
                    </button>
                  ))}
                </div>
                <div className="text-xs font-medium text-muted-foreground">
                  Рёбра графа
                </div>
                <div className="max-h-52 space-y-2 overflow-auto rounded border p-2">
                  {parsedGraph.edges.map((edge, idx) => (
                    <button
                      key={`${edge.from}-${edge.to}-${idx}`}
                      type="button"
                      className={`w-full rounded border p-2 text-left text-xs ${selection?.kind === "edge" && selection.idx === idx ? "border-blue-500 bg-blue-50" : ""}`}
                      onClick={() => setSelection({ kind: "edge", idx })}
                    >
                      <div className="font-medium">
                        {edge.from} → {edge.to}
                      </div>
                      {edge.condition ? (
                        <div className="text-muted-foreground">
                          условие: {edge.condition}
                        </div>
                      ) : null}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-2 rounded border p-2">
                <div className="text-xs font-medium text-muted-foreground">
                  Свойства выбранного
                </div>
                {selectedEdge && selection?.kind === "edge" ? (
                  <>
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        className="rounded border px-1 py-0.5"
                        value={selectedEdge.from}
                        onChange={(e) =>
                          updateEdge(selection.idx, { from: e.target.value })
                        }
                      >
                        {parsedGraph.nodes.map((node, nodeIdx) => (
                          <option key={`from-${node.id}-${nodeIdx}`}>
                            {node.id}
                          </option>
                        ))}
                      </select>
                      <select
                        className="rounded border px-1 py-0.5"
                        value={selectedEdge.to}
                        onChange={(e) =>
                          updateEdge(selection.idx, { to: e.target.value })
                        }
                      >
                        {parsedGraph.nodes.map((node, nodeIdx) => (
                          <option key={`to-${node.id}-${nodeIdx}`}>
                            {node.id}
                          </option>
                        ))}
                      </select>
                    </div>
                    <input
                      className="w-full rounded border px-1 py-0.5"
                      value={selectedEdge.condition ?? ""}
                      onChange={(e) =>
                        updateEdge(selection.idx, {
                          condition: e.target.value || undefined,
                        })
                      }
                      placeholder="Условие (необязательно)"
                    />
                    <button
                      className="rounded border px-2 py-0.5"
                      onClick={() => removeEdge(selection.idx)}
                    >
                      Удалить ребро
                    </button>
                  </>
                ) : selectedNode ? (
                  <>
                    <input
                      className="w-full rounded border px-2 py-1"
                      value={selectedNode.id}
                      onChange={(e) =>
                        updateNode(selectedNode.id, { id: e.target.value })
                      }
                    />
                    <select
                      className="w-full rounded border px-2 py-1"
                      value={selectedNode.type}
                      onChange={(e) =>
                        updateNode(selectedNode.id, { type: e.target.value })
                      }
                    >
                      {NODE_TYPES.map((kind) => (
                        <option key={kind}>{kind}</option>
                      ))}
                    </select>
                    <textarea
                      className="h-32 w-full rounded border p-2 font-mono text-xs"
                      value={configText}
                      onChange={(e) => {
                        setConfigText(e.target.value);
                        try {
                          const nextConfig = JSON.parse(
                            e.target.value,
                          ) as Record<string, unknown>;
                          updateNode(selectedNode.id, { config: nextConfig });
                        } catch {
                          // keep local text invalid until corrected
                        }
                      }}
                    />
                    <button
                      className="rounded border px-2 py-1"
                      onClick={() => removeNode(selectedNode.id)}
                    >
                      Удалить ноду
                    </button>
                  </>
                ) : (
                  <div className="text-xs text-muted-foreground">
                    Выберите узел или ребро для редактирования.
                  </div>
                )}
              </div>
            </div>
            <details>
              <summary className="cursor-pointer text-xs text-muted-foreground">
                Предпросмотр JSON
              </summary>
              <pre className="mt-2 max-h-48 overflow-auto rounded border bg-muted/30 p-2 text-[11px]">
                {JSON.stringify(parsedGraph, null, 2)}
              </pre>
            </details>
          </div>
          {validationError ? (
            <p className="text-xs text-amber-700">{validationError}</p>
          ) : null}
          {error ? <p className="text-xs text-red-600">{error}</p> : null}
          <button
            className="rounded border px-3 py-1 disabled:opacity-60"
            disabled={Boolean(validationError)}
            onClick={() => save().catch(() => undefined)}
          >
            Сохранить профиль
          </button>
        </div>
        <div className="rounded border p-3 text-sm">
          <h2 className="mb-2 font-medium">Профили</h2>
          <ErrorState
            error={profilesError ?? undefined}
            onRetry={() => void load()}
          />
          {profilesLoading ? (
            <LoadingScreen label="Загрузка профилей пайплайна" />
          ) : null}
          {!profilesLoading && !profilesError && profiles.length === 0 ? (
            <EmptyState
              title="Профили пайплайна не найдены"
              description="Создайте первый профиль через builder слева или повторите загрузку позже."
            />
          ) : null}
          {!profilesLoading && !profilesError && profiles.length > 0 ? (
            <div className="space-y-2">
              {profiles.map((profile) => (
                <div key={profile.id} className="rounded border p-2">
                  <div className="font-medium">{profile.code}</div>
                  <div className="text-xs text-muted-foreground">
                    v{profile.profile_version} · {profile.name}
                  </div>
                  <div className="text-xs">
                    узлов: {profile.graph?.nodes?.length ?? 0}, рёбер:{" "}
                    {profile.graph?.edges?.length ?? 0}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
};

export default PipelineBuilderPage;
