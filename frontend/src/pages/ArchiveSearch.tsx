import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchSearch, type SearchItem, type SearchType } from "@/api/search";
import { useDebounce } from "@/hooks/useDebounce";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const tabs: { label: string; value: SearchType | "all" }[] = [
  { label: "Все", value: "all" },
  { label: "Документы", value: "documents" },
  { label: "Файлы", value: "files" },
  { label: "Задачи", value: "jobs" },
  { label: "Справочники", value: "templates" },
];

const ArchiveSearch = () => {
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState<SearchItem[]>([]);
  const q = params.get("q") ?? "";
  const type = (params.get("type") as SearchType | "all" | null) ?? "all";
  const siteId = params.get("site_id") ?? "";
  const status = params.get("status") ?? "";
  const projectId = params.get("project_id") ?? "";
  const contractorId = params.get("contractor_id") ?? "";
  const debouncedQ = useDebounce(q, 400);

  const activeTypes = useMemo(() => (type === "all" ? undefined : [type]), [type]);

  const patchParams = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([key, value]) => {
      if (value) next.set(key, value);
      else next.delete(key);
    });
    setParams(next);
  };

  useEffect(() => {
    fetchSearch({
      q: debouncedQ,
      types: activeTypes,
      site_id: siteId || undefined,
      status: status || undefined,
      project_id: projectId || undefined,
      contractor_id: contractorId || undefined,
    })
      .then((result) => setItems(result.items))
      .catch(() => setItems([]));
  }, [debouncedQ, activeTypes, siteId, status, projectId, contractorId]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Архив / Поиск</h1>
      <Input value={q} onChange={(e) => patchParams({ q: e.target.value })} placeholder="Поиск по метаданным и содержимому" />
      <div className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <Button key={tab.value} variant={type === tab.value ? "default" : "outline"} size="sm" onClick={() => patchParams({ type: tab.value })}>
            {tab.label}
          </Button>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
        <Input value={siteId} onChange={(e) => patchParams({ site_id: e.target.value })} placeholder="site_id" />
        <Input value={projectId} onChange={(e) => patchParams({ project_id: e.target.value })} placeholder="project_id" />
        <Input value={contractorId} onChange={(e) => patchParams({ contractor_id: e.target.value })} placeholder="contractor_id" />
        <Input value={status} onChange={(e) => patchParams({ status: e.target.value })} placeholder="status" />
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left">
            <th>Заголовок</th>
            <th>Тип</th>
            <th>Фрагмент</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.entity_type}-${item.entity_id}`} className="border-t align-top">
              <td className="py-2"><a className="text-primary underline" href={item.deeplink ?? "#"}>{item.title}</a></td>
              <td className="py-2">{item.entity_type}</td>
              <td className="py-2 text-muted-foreground" dangerouslySetInnerHTML={{ __html: item.snippet ?? "—" }} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ArchiveSearch;
