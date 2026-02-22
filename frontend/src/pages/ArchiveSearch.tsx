import { useEffect, useState } from "react";

import { searchGlobal, type SearchItem } from "@/api/search";
import { fetchDownloadUrl } from "@/api/files";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const ArchiveSearch = () => {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<SearchItem[]>([]);

  useEffect(() => {
    searchGlobal(q || "pdf").then((result) => setItems(result.items)).catch(() => setItems([]));
  }, [q]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Архив / Поиск</h1>
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по метаданным и содержимому" />
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left">
            <th>filename</th>
            <th>status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-t">
              <td>{item.title}</td>
              <td>ready</td>
              <td>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    const [fileId, versionId] = item.id.split(":");
                    if (!versionId) return;
                    const url = await fetchDownloadUrl(fileId, versionId);
                    window.open(url, "_blank", "noopener,noreferrer");
                  }}
                >
                  Download
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ArchiveSearch;
