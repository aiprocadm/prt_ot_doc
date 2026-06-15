import { useEffect } from "react";

import { CommandCenterPanel } from "@/components/operational/CommandCenterPanel";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { useOperationalDashboardStore } from "@/stores/operationalDashboard";

const POLL_INTERVAL_MS = 30_000;

export function CommandCenterPage() {
  const data = useOperationalDashboardStore((state) => state.data);
  const loading = useOperationalDashboardStore((state) => state.loading);
  const error = useOperationalDashboardStore((state) => state.error);
  const fetchDashboard = useOperationalDashboardStore((state) => state.fetchDashboard);

  useEffect(() => {
    void fetchDashboard();
    const timer = setInterval(() => void fetchDashboard(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchDashboard]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") void fetchDashboard();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [fetchDashboard]);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Командный центр" }]} />
      <CommandCenterPanel
        data={data}
        loading={loading}
        error={error}
        onRefresh={() => void fetchDashboard()}
      />
    </div>
  );
}

export default CommandCenterPage;
