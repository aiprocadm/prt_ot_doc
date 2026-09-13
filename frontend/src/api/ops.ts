import { apiClient } from "@/api/client";
import { allowedOr, type PartialLoad } from "@/api/partial";
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
  company_id?: string;
  site_id?: string | null;
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
  /** Срез-167: разделы, закрытые правами. Пусто — значит видно всё. */
  denied: string[];
};

export type CreatePpeIssuePayload = {
  person_id: string;
  item_id: string;
  quantity: number;
  wear_days?: number;
  expires_at?: string;
  issued_at?: string;
};

export type FindingDto = {
  id: string;
  title: string;
  status: string;
  severity: string;
  source_type: string;
  source_id: string;
  finding_type: string;
  due_date?: string | null;
  site_id?: string | null;
  description?: string | null;
  created_at?: string | null;
};

export type CorrectiveActionDto = {
  id: string;
  title: string;
  status: string;
  source_type: string;
  source_id: string;
  action_type: string;
  due_date?: string | null;
  responsible_user_id?: string | null;
  site_id?: string | null;
  effectiveness_status?: string | null;
  description?: string | null;
  completed_at?: string | null;
};

export type AuditPrepSnapshot = {
  inspections: InspectionDto[];
  prescriptions: PrescriptionDto[];
  overdueTasks: TaskDto[];
  /** Срез-167: разделы, закрытые правами. Пусто — значит видно всё. */
  denied: string[];
};

export const opsApi = {
  async getPpeOverview(): Promise<PpeOverviewSnapshot> {
    // Срез-167: раньше один отказ по правам гасил весь экран. Теперь каждый
    // список грузится отдельно, а закрытые разделы называются словами.
    const state: PartialLoad = { denied: [] };
    const empty = { data: { items: [] } } as { data: { items: never[] } };
    const [itemsResponse, issuesResponse, expiringResponse, personsResponse] =
      await Promise.all([
        allowedOr(
          state,
          "номенклатура СИЗ",
          apiClient.get<PageResponse<PpeItemDto>>("/ppe/items", {
            params: { limit: 100, offset: 0 },
          }),
          empty as never,
        ),
        allowedOr(
          state,
          "выдачи СИЗ",
          apiClient.get<PageResponse<PpeIssueDto>>("/ppe/issues", {
            params: { limit: 100, offset: 0 },
          }),
          empty as never,
        ),
        allowedOr(
          state,
          "истекающие сроки носки",
          apiClient.get<PageResponse<PpeIssueDto>>("/ppe/issues/expiring", {
            params: { within_days: 30 },
          }),
          empty as never,
        ),
        allowedOr(
          state,
          "сотрудники",
          apiClient.get<PageResponse<PersonDto>>("/persons", {
            params: { page: 1, page_size: 100 },
          }),
          empty as never,
        ),
      ]);

    return {
      items: itemsResponse.data.items ?? [],
      issues: issuesResponse.data.items ?? [],
      expiring: expiringResponse.data.items ?? [],
      persons: personsResponse.data.items ?? [],
      denied: state.denied,
    };
  },

  async createPpeIssue(payload: CreatePpeIssuePayload): Promise<PpeIssueDto> {
    const response = await apiClient.post<PpeIssueDto>("/ppe/issues", payload);
    return response.data;
  },

  async getPrescriptions(): Promise<PrescriptionDto[]> {
    const response = await apiClient.get<PageResponse<PrescriptionDto>>(
      "/prescriptions",
      { params: { limit: 100, offset: 0 } },
    );
    return response.data.items ?? [];
  },

  async getFindings(): Promise<FindingDto[]> {
    const response = await apiClient.get<FindingDto[]>("/findings");
    return response.data ?? [];
  },

  async getCorrectiveActions(): Promise<CorrectiveActionDto[]> {
    const response = await apiClient.get<CorrectiveActionDto[]>(
      "/corrective-actions",
    );
    return response.data ?? [];
  },

  async getAuditPrepSnapshot(): Promise<AuditPrepSnapshot> {
    const state: PartialLoad = { denied: [] };
    const empty = { data: { items: [] } } as { data: { items: never[] } };
    const [inspectionsResponse, prescriptionsResponse, tasksResponse] =
      await Promise.all([
        allowedOr(
          state,
          "проверки",
          apiClient.get<PageResponse<InspectionDto>>("/inspections", {
            params: { limit: 100, offset: 0 },
          }),
          empty as never,
        ),
        allowedOr(
          state,
          "предписания",
          apiClient.get<PageResponse<PrescriptionDto>>("/prescriptions", {
            params: { limit: 100, offset: 0 },
          }),
          empty as never,
        ),
        allowedOr(
          state,
          "просроченные задачи",
          apiClient.get<PageResponse<TaskDto>>("/tasks", {
            params: { overdue: true, page: 1, page_size: 100 },
          }),
          empty as never,
        ),
      ]);

    return {
      inspections: inspectionsResponse.data.items ?? [],
      prescriptions: prescriptionsResponse.data.items ?? [],
      overdueTasks: tasksResponse.data.items ?? [],
      denied: state.denied,
    };
  },
};
