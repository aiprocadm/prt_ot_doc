import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";

type GraphNode = { id: string; type: string; config?: Record<string, unknown> };
type GraphEdge = { from: string; to: string; condition?: string };
type PipelineProfile = { id: string; code: string; name: string; profile_version: number; graph?: { nodes: GraphNode[]; edges: GraphEdge[] } };

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
  "noop"
] as const;

const defaultGraph: { nodes: GraphNode[]; edges: GraphEdge[] } = {
  nodes: [
    { id: "render", type: "render_docx", config: { template_code: "default" } },
    { id: "headers", type: "apply_headers" },
    { id: "replace", type: "replace_apply" },
    { id: "pdf", type: "convert_pdf" }
  ],
  edges: [
    { from: "render", to: "headers" },
    { from: "headers", to: "replace" },
    { from: "replace", to: "pdf" }
  ]
};

const PipelineBuilderPage = () => {
  const [profiles, setProfiles] = useState<PipelineProfile[]>([]);
  const [code, setCode] = useState("doc-default");
  const [name, setName] = useState("Default pipeline");
  const [graph, setGraph] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] }>(defaultGraph);
  const [selectedNodeId, setSelectedNodeId] = useState(defaultGraph.nodes[0]?.id ?? "");
  const [configText, setConfigText] = useState(JSON.stringify(defaultGraph.nodes[0]?.config ?? {}, null, 2));
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    const response = await apiClient.get<PipelineProfile[]>("/v1/pipelines/profiles");
    setProfiles(response.data);
  };

  useEffect(() => {
    load().catch(() => setProfiles([]));
  }, []);

  const parsedGraph = graph;

  const validationError = useMemo(() => {
    const ids = parsedGraph.nodes.map((n) => n.id);
    if (new Set(ids).size !== ids.length) return "Есть дубли id нод";
    const idSet = new Set(ids);
    const badEdge = parsedGraph.edges.find((e) => !idSet.has(e.from) || !idSet.has(e.to));
    if (badEdge) return `Ребро ${badEdge.from} → ${badEdge.to} ссылается на неизвестную ноду`;
    return null;
  }, [parsedGraph]);

  const selectedNode = useMemo(
    () => parsedGraph.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [parsedGraph.nodes, selectedNodeId]
  );

  useEffect(() => {
    setConfigText(JSON.stringify(selectedNode?.config ?? {}, null, 2));
  }, [selectedNode]);

  const addNode = () => {
    const nextIdx = parsedGraph.nodes.length + 1;
    const node: GraphNode = { id: `node_${nextIdx}`, type: "noop", config: {} };
    setGraph((prev) => ({ ...prev, nodes: [...prev.nodes, node] }));
    setSelectedNodeId(node.id);
  };

  const addEdge = () => {
    if (parsedGraph.nodes.length < 2) return;
    const fallbackFrom = parsedGraph.nodes[parsedGraph.nodes.length - 2]?.id ?? parsedGraph.nodes[0].id;
    const fallbackTo = parsedGraph.nodes[parsedGraph.nodes.length - 1]?.id ?? parsedGraph.nodes[0].id;
    setGraph((prev) => ({ ...prev, edges: [...prev.edges, { from: fallbackFrom, to: fallbackTo }] }));
  };

  const updateNode = (nodeId: string, patch: Partial<GraphNode>) => {
    setGraph((prev) => {
      const nextNodes = prev.nodes.map((node) => (node.id === nodeId ? { ...node, ...patch } : node));
      const nextNodeId = patch.id ?? nodeId;
      const nextEdges =
        patch.id && patch.id !== nodeId
          ? prev.edges.map((edge) => ({
              ...edge,
              from: edge.from === nodeId ? nextNodeId : edge.from,
              to: edge.to === nodeId ? nextNodeId : edge.to
            }))
          : prev.edges;
      return { ...prev, nodes: nextNodes, edges: nextEdges };
    });
    if (patch.id) {
      setSelectedNodeId(patch.id);
    }
  };

  const removeNode = (nodeId: string) => {
    setGraph((prev) => ({
      nodes: prev.nodes.filter((n) => n.id !== nodeId),
      edges: prev.edges.filter((e) => e.from !== nodeId && e.to !== nodeId)
    }));
    setSelectedNodeId("");
  };

  const updateEdge = (idx: number, patch: Partial<GraphEdge>) => {
    setGraph((prev) => ({
      ...prev,
      edges: prev.edges.map((edge, edgeIdx) => (edgeIdx === idx ? { ...edge, ...patch } : edge))
    }));
  };

  const removeEdge = (idx: number) => {
    setGraph((prev) => ({ ...prev, edges: prev.edges.filter((_, edgeIdx) => edgeIdx !== idx) }));
  };

  const save = async () => {
    try {
      setError(null);
      if (validationError) throw new Error(validationError);
      await apiClient.post("/v1/pipelines/profiles", { code, name, graph: parsedGraph, is_active: true });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка сохранения");
    }
  };

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Low-code Process Builder</h1>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2 rounded border p-3 text-sm">
          <input className="w-full rounded border px-2 py-1" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Code" />
          <input className="w-full rounded border px-2 py-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" />
          <div className="space-y-2 rounded border p-2">
            <div className="flex flex-wrap gap-2">
              <button className="rounded border px-2 py-1" onClick={addNode}>+ Нода</button>
              <button className="rounded border px-2 py-1" onClick={addEdge}>+ Ребро</button>
            </div>
            <div className="grid gap-3 lg:grid-cols-[1.3fr_1fr]">
              <div className="space-y-2">
                <div className="text-xs font-medium text-muted-foreground">Canvas (nodes + links)</div>
                <div className="max-h-52 space-y-2 overflow-auto rounded border p-2">
                  {parsedGraph.nodes.map((node) => (
                    <button
                      key={node.id}
                      type="button"
                      className={`w-full rounded border p-2 text-left text-xs ${selectedNodeId === node.id ? "border-blue-500 bg-blue-50" : ""}`}
                      onClick={() => setSelectedNodeId(node.id)}
                    >
                      <div className="font-medium">{node.id}</div>
                      <div className="text-muted-foreground">{node.type}</div>
                    </button>
                  ))}
                </div>
                <div className="text-xs font-medium text-muted-foreground">Edges</div>
                <div className="max-h-52 space-y-2 overflow-auto rounded border p-2">
                  {parsedGraph.edges.map((edge, idx) => (
                    <div key={`${edge.from}-${edge.to}-${idx}`} className="space-y-1 rounded border p-2">
                      <div className="grid grid-cols-2 gap-2">
                        <select className="rounded border px-1 py-0.5" value={edge.from} onChange={(e) => updateEdge(idx, { from: e.target.value })}>
                          {parsedGraph.nodes.map((node) => <option key={`${idx}-from-${node.id}`}>{node.id}</option>)}
                        </select>
                        <select className="rounded border px-1 py-0.5" value={edge.to} onChange={(e) => updateEdge(idx, { to: e.target.value })}>
                          {parsedGraph.nodes.map((node) => <option key={`${idx}-to-${node.id}`}>{node.id}</option>)}
                        </select>
                      </div>
                      <input className="w-full rounded border px-1 py-0.5" value={edge.condition ?? ""} onChange={(e) => updateEdge(idx, { condition: e.target.value || undefined })} placeholder="condition (optional)" />
                      <button className="rounded border px-2 py-0.5" onClick={() => removeEdge(idx)}>Удалить ребро</button>
                    </div>
                  ))}
                </div>
              </div>
              <div className="space-y-2 rounded border p-2">
                <div className="text-xs font-medium text-muted-foreground">Node inspector</div>
                {selectedNode ? (
                  <>
                    <input className="w-full rounded border px-2 py-1" value={selectedNode.id} onChange={(e) => updateNode(selectedNode.id, { id: e.target.value })} />
                    <select className="w-full rounded border px-2 py-1" value={selectedNode.type} onChange={(e) => updateNode(selectedNode.id, { type: e.target.value })}>
                      {NODE_TYPES.map((kind) => <option key={kind}>{kind}</option>)}
                    </select>
                    <textarea
                      className="h-32 w-full rounded border p-2 font-mono text-xs"
                      value={configText}
                      onChange={(e) => {
                        setConfigText(e.target.value);
                        try {
                          const nextConfig = JSON.parse(e.target.value) as Record<string, unknown>;
                          updateNode(selectedNode.id, { config: nextConfig });
                        } catch {
                          // keep local text invalid until corrected
                        }
                      }}
                    />
                    <button className="rounded border px-2 py-1" onClick={() => removeNode(selectedNode.id)}>Удалить ноду</button>
                  </>
                ) : <div className="text-xs text-muted-foreground">Выберите ноду для редактирования.</div>}
              </div>
            </div>
            <details>
              <summary className="cursor-pointer text-xs text-muted-foreground">JSON preview</summary>
              <pre className="mt-2 max-h-48 overflow-auto rounded border bg-muted/30 p-2 text-[11px]">{JSON.stringify(parsedGraph, null, 2)}</pre>
            </details>
          </div>
          {validationError ? <p className="text-xs text-amber-700">{validationError}</p> : null}
          {error ? <p className="text-xs text-red-600">{error}</p> : null}
          <button className="rounded border px-3 py-1 disabled:opacity-60" disabled={Boolean(validationError)} onClick={() => save().catch(() => undefined)}>Сохранить профиль</button>
        </div>
        <div className="rounded border p-3 text-sm">
          <h2 className="mb-2 font-medium">Профили</h2>
          <div className="space-y-2">
            {profiles.map((profile) => (
              <div key={profile.id} className="rounded border p-2">
                <div className="font-medium">{profile.code}</div>
                <div className="text-xs text-muted-foreground">v{profile.profile_version} · {profile.name}</div>
                <div className="text-xs">nodes: {profile.graph?.nodes?.length ?? 0}, edges: {profile.graph?.edges?.length ?? 0}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default PipelineBuilderPage;
