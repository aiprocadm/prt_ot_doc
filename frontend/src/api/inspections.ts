import { apiClient } from "@/api/client";

export type InspectionResult = {
  id: string;
  inspection_id: string;
  title: string;
  outcome: string | null;
  notes: string | null;
  issued_at: string | null;
  file_id: string | null;
  created_at: string;
};

export type Inspection = {
  id: string;
  company_id: string;
  site_id: string | null;
  inspection_type: string;
  responsible_id: string | null;
  recurrence_rule: string | null;
  authority: string;
  purpose: string | null;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  result_summary: string | null;
  results: InspectionResult[];
};

export type InspectionPage = {
  items: Inspection[];
  total: number;
};

export const inspectionsApi = {
  list: async (params?: {
    company_id?: string;
    site_id?: string;
    status_filter?: string;
    inspection_type?: string;
    responsible_id?: string;
    limit?: number;
    offset?: number;
  }) => {
    const { data } = await apiClient.get<InspectionPage>("/inspections", { params });
    return data;
  },
  listResults: async (inspectionId: string) => {
    const { data } = await apiClient.get<InspectionResult[]>(`/inspections/${inspectionId}/results`);
    return data;
  },
  create: async (payload: {
    company_id: string;
    site_id?: string;
    inspection_type: string;
    authority: string;
    purpose?: string;
    scheduled_at?: string;
  }) => {
    const { data } = await apiClient.post<Inspection>("/inspections", payload);
    return data;
  }
};
