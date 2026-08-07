import { apiClient } from "@/api/client";

export type Incident = {
  id: string;
  title: string;
  description: string | null;
  incident_type: string;
  occurred_at: string;
  company_id: string;
  site_id: string;
  severity: string;
  status: string;
  investigation_stage: string;
  location_description: string | null;
  pack_id: string | null;
  victim_ids: string[];
};

export type IncidentPage = {
  items: Incident[];
  total: number;
};

export type IncidentLog = {
  id: string;
  incident_id: string;
  author_id: string | null;
  stage: string;
  status: string;
  message: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export const incidentsApi = {
  list: async (params?: {
    company_id?: string;
    site_id?: string;
    status_filter?: string;
    incident_type?: string;
    limit?: number;
    offset?: number;
  }) => {
    const { data } = await apiClient.get<IncidentPage>("/incidents", {
      params,
    });
    return data;
  },
  listLogs: async (incidentId: string) => {
    const { data } = await apiClient.get<IncidentLog[]>(
      `/incidents/${incidentId}/logs`,
    );
    return data;
  },
  create: async (payload: {
    title: string;
    description?: string;
    incident_type: string;
    occurred_at: string;
    company_id: string;
    site_id?: string;
    severity: string;
  }) => {
    const { data } = await apiClient.post<Incident>("/incidents", payload);
    return data;
  },
};
