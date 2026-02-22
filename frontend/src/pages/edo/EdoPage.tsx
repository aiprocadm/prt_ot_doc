import { useEffect, useState } from "react";

import { edoApi, type EdoEnvelope } from "@/api/edo";

const EdoPage = () => {
  const [items, setItems] = useState<EdoEnvelope[]>([]);
  useEffect(() => {
    edoApi.list().then(setItems).catch(() => undefined);
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">ЭДО</h1>
      {items.map((it) => (
        <div key={it.id} className="rounded border p-3 text-sm">
          <div>{it.id.slice(0, 8)} — {it.status}</div>
          <div className="text-muted-foreground">external_id: {it.external_id ?? "—"}</div>
        </div>
      ))}
    </div>
  );
};

export default EdoPage;
