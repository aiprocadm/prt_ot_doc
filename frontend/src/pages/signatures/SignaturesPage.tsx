import { useEffect, useState } from "react";

import { signApi, type SignatureRequest } from "@/api/sign";

const SignaturesPage = () => {
  const [items, setItems] = useState<SignatureRequest[]>([]);
  useEffect(() => {
    signApi.list().then(setItems).catch(() => undefined);
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Подписи</h1>
      {items.map((it) => (
        <div key={it.id} className="rounded border p-3 text-sm">
          <div>{it.id.slice(0, 8)} — {it.status}</div>
          <div className="text-muted-foreground">provider: {it.provider}</div>
        </div>
      ))}
    </div>
  );
};

export default SignaturesPage;
