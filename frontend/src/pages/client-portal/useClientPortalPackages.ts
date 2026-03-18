import { useCallback, useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";

export type PortalRun = {
  id: string;
  status: string;
  client_company_id?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

export type PortalFile = {
  kind: string;
  signed_url?: string;
  sha256?: string;
  size?: number | null;
};

export type PortalEvent = {
  id: string;
  type: string;
  created_at: string;
};

export type PortalTicket = {
  id: string;
  title: string;
  status: string;
  created_at: string;
};

export type PortalDetail = {
  run: PortalRun;
  history: {
    status_flow: string[];
    events_count: number;
    tickets_count: number;
    requirements_total: number;
    requirements_missing: number;
  };
  files: PortalFile[];
  events: PortalEvent[];
  tickets: PortalTicket[];
};

export const useClientPortalPackages = () => {
  const [items, setItems] = useState<PortalRun[]>([]);
  const [selected, setSelected] = useState<PortalDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const selectRun = useCallback(async (runId: string) => {
    const detail = await apiClient.get<PortalDetail>(`/client-portal/packages/${runId}`);
    setSelected(detail.data);
    return detail.data;
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get<PortalRun[]>("/client-portal/packages");
      setItems(data);
      if (data[0]) {
        await selectRun(data[0].id);
      } else {
        setSelected(null);
      }
    } finally {
      setLoading(false);
    }
  }, [selectRun]);

  useEffect(() => {
    void load();
  }, [load]);

  const summary = useMemo(() => {
    return {
      packagesTotal: items.length,
      filesTotal: selected?.files.length ?? 0,
      eventsTotal: selected?.history.events_count ?? 0,
      requestsTotal: selected?.history.tickets_count ?? 0,
      openRequirements: selected?.history.requirements_missing ?? 0,
      activeRunId: selected?.run.id ?? null,
      packageStatuses: items.map((item) => item.status)
    };
  }, [items, selected]);

  return { items, selected, loading, load, selectRun, summary };
};
