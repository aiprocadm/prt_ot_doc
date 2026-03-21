import { apiClient } from "@/api/client";
import type { PersonDto } from "@/types/dto/persons";
import type { TaskDto } from "@/types/dto/tasks";

export type PpeItemDto = {
  id: string;
  name: string;
  code: string;
  category: string;
  description?: string | null;
  default_wear_days?: number | null;
  metadata_json?: Record<string, unknown> | null;
};

export type PpeIssueDto = {
  id: string;
  person_id: string;
  item_id: string;
  quantity: number;
  status: string;
  issued_at?: string | null;
  expires_at?: string | null;
  returned_at?: string | null;
};

export type PrescriptionDto = {
  id: string;
  inspection_id: string;
  incident_id?: string | null;
  description: string;
  due_at?: string | null;
  status: string;
  assignee_id?: string | null;
};

export type InspectionDto = {
  id: string;
  authority?: string | null;
  purpose?: string | null;
  scheduled_at?: string | null;
  status: string;
  inspection_type?: string | null;
  result_summary?: string | null;
};

type PageResponse<T> = {
  items: T[];
  total: number;
};

export type PpeOverviewSnapshot = {
  items: PpeItemDto[];
  issues: PpeIssueDto[];
  expiring: PpeIssueDto[];
  persons: PersonDto[];
};

export type AuditPrepSnapshot = {
  inspections: InspectionDto[];
  prescriptions: PrescriptionDto[];
  overdueTasks: TaskDto[];
};

export const opsApi = {
  async getPpeOverview(): Promise<PpeOverviewSnapshot> {
    const [itemsResponse, issuesResponse, expiringResponse, personsResponse] = await Promise.all([
      apiClient.get<PageResponse<PpeItemDto>>("/ppe/items", { params: { limit: 100, offset: 0 } }),
      apiClient.get<PageResponse<PpeIssueDto>>("/ppe/issues", { params: { limit: 100, offset: 0 } }),
      apiClient.get<PageResponse<PpeIssueDto>>("/ppe/issues/expiring", { params: { within_days: 30 } }),
      apiClient.get<PageResponse<PersonDto>>("/persons", { params: { page: 1, page_size: 100 } })
    ]);

    return {
      items: itemsResponse.data.items ?? [],
      issues: issuesResponse.data.items ?? [],
      expiring: expiringResponse.data.items ?? [],
      persons: personsResponse.data.items ?? []
    };
  },

  async getPrescriptions(): Promise<PrescriptionDto[]> {
    const response = await apiClient.get<PageResponse<PrescriptionDto>>("/prescriptions", { params: { limit: 100, offset: 0 } });
    return response.data.items ?? [];
  },

  async getAuditPrepSnapshot(): Promise<AuditPrepSnapshot> {
    const [inspectionsResponse, prescriptionsResponse, tasksResponse] = await Promise.all([
      apiClient.get<PageResponse<InspectionDto>>("/inspections", { params: { limit: 100, offset: 0 } }),
      apiClient.get<PageResponse<PrescriptionDto>>("/prescriptions", { params: { limit: 100, offset: 0 } }),
      apiClient.get<PageResponse<TaskDto>>("/tasks", { params: { overdue: true, page: 1, page_size: 100 } })
    ]);

    return {
      inspections: inspectionsResponse.data.items ?? [],
      prescriptions: prescriptionsResponse.data.items ?? [],
      overdueTasks: tasksResponse.data.items ?? []
    };
  }
};
