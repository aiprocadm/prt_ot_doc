import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";

type GraphNode = { id: string; type: string; config?: Record<string, unknown> };
type GraphEdge = { from: string; to: string; condition?: string };
type PipelineProfile = { id: string; code: string; name: string; profile_version: number; graph?: { nodes: GraphNode[]; edges: GraphEdge[] } };

const defaultGraph = {
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
  const [graphText, setGraphText] = useState(JSON.stringify(defaultGraph, null, 2));
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    const response = await apiClient.get<PipelineProfile[]>("/v1/pipelines/profiles");
    setProfiles(response.data);
  };

  useEffect(() => {
    load().catch(() => setProfiles([]));
  }, []);

  const parsedGraph = useMemo(() => {
    try {
      return JSON.parse(graphText) as { nodes: GraphNode[]; edges: GraphEdge[] };
    } catch {
      return null;
    }
  }, [graphText]);

  const validationError = useMemo(() => {
    if (!parsedGraph) return "Граф невалидный JSON";
    const ids = parsedGraph.nodes.map((n) => n.id);
    if (new Set(ids).size !== ids.length) return "Есть дубли id нод";
    const idSet = new Set(ids);
    const badEdge = parsedGraph.edges.find((e) => !idSet.has(e.from) || !idSet.has(e.to));
    if (badEdge) return `Ребро ${badEdge.from} → ${badEdge.to} ссылается на неизвестную ноду`;
    return null;
  }, [parsedGraph]);

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
          <textarea className="h-72 w-full rounded border p-2 font-mono text-xs" value={graphText} onChange={(e) => setGraphText(e.target.value)} />
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
