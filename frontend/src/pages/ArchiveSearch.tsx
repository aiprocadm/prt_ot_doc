import { useEffect, useState } from "react";

import { fetchSearch, type SearchItem, type SearchType } from "@/api/search";
import { useDebounce } from "@/hooks/useDebounce";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const tabs: { label: string; value: SearchType }[] = [
  { label: "Документы", value: "documents" },
  { label: "Люди", value: "people" },
  { label: "Объекты", value: "sites" },
  { label: "Риски", value: "risk" },
  { label: "СИЗ", value: "ppe" },
  { label: "Обучение", value: "training" },
  { label: "Инциденты", value: "incidents" },
  { label: "Проверки", value: "inspections" },
];

const ArchiveSearch = () => {
  const [q, setQ] = useState("");
  const [type, setType] = useState<SearchType>("documents");
  const [siteId, setSiteId] = useState("");
  const [status, setStatus] = useState("");
  const [items, setItems] = useState<SearchItem[]>([]);
  const debouncedQ = useDebounce(q, 400);

  useEffect(() => {
    fetchSearch({ q: debouncedQ, types: [type], site_id: siteId || undefined, status: status || undefined })
      .then((result) => setItems(result.items))
      .catch(() => setItems([]));
  }, [debouncedQ, type, siteId, status]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Архив / Поиск</h1>
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по метаданным и содержимому" />
      <div className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <Button key={tab.value} variant={type === tab.value ? "default" : "outline"} size="sm" onClick={() => setType(tab.value)}>
            {tab.label}
          </Button>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
        <Input value={siteId} onChange={(e) => setSiteId(e.target.value)} placeholder="site_id" />
        <Input value={status} onChange={(e) => setStatus(e.target.value)} placeholder="status" />
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
              <td className="py-2">{item.title}</td>
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
