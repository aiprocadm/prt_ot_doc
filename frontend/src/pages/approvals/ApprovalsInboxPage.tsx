import { useEffect } from "react";

import { apiClient } from "@/lib/apiClient";

const ApprovalsInboxPage = () => {
  useEffect(() => {
    apiClient.get("/approvals/routes").catch(() => undefined);
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Согласования: Входящие</h1>
      <div className="rounded-lg border bg-card p-4 text-sm text-muted-foreground">MVP inbox согласований</div>
    </div>
  );
};

export default ApprovalsInboxPage;
