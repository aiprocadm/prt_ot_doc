import { apiClient } from "@/api/client";
import { briefingsApi, type BriefingEntryDto, type BriefingJournalDto, type BriefingTemplateDto } from "@/api/briefings";
import { opsApi, type CorrectiveActionDto, type InspectionDto, type PrescriptionDto, type PpeItemDto } from "@/api/ops";
import type { PersonDto } from "@/types/dto/persons";
import type { TaskDto } from "@/types/dto/tasks";

export type CompanyDto = {
  id: string;
  name: string;
  activity_type?: string | null;
  work_types?: string[];
  hazardous_factors?: string[];
  contact_person?: string | null;
  contact_phone?: string | null;
  is_hazardous_production_facility?: boolean;
  has_dangerous_objects?: boolean;
};

export type SiteDto = {
  id: string;
  company_id: string;
  name: string;
  address?: string | null;
  hazard_class?: string | null;
  contact_name?: string | null;
  is_hazardous_production_facility?: boolean;
};

export type ContractDto = {
  id: string;
  company_id: string;
  status: string;
  number?: string | null;
  expires_at?: string | null;
};

export type TrainingProgramDto = {
  id: string;
  title?: string;
  code?: string | null;
  status?: string;
};

export type TemplateDto = {
  id: string;
  name?: string;
  code?: string | null;
  scope?: string | null;
  is_active?: boolean;
};

export type TenancyContextDto = {
  tenant: { id: string; slug: string; code?: string | null; schema_name?: string | null };
  quota?: { max_parallel_jobs?: number; max_doc_generations_per_month?: number; max_storage_mb?: number } | null;
  usage?: { yyyymm?: string; doc_generations?: number } | null;
  correlation_id?: string | null;
};

export type NotificationSettingsDto = {
  email_enabled?: boolean;
  telegram_enabled?: boolean;
  digest_enabled?: boolean;
  reminder_window_days?: number;
};

export type ApiTokenDto = {
  id: string;
  name: string;
  scopes: string[];
  created_at: string;
  expires_at?: string | null;
  is_revoked: boolean;
};

export type MedicalExamDto = {
  id: string;
  person_id: string;
  exam_type: string;
  exam_date: string;
  conclusion?: string | null;
  valid_until: string;
  created_at: string;
  updated_at: string;
};

export type OutboxDto = { id: string; status: string; event_type: string; destination: string; attempts: number; created_at: string };
export type WebhookEndpointDto = { id: string; code?: string | null; target_url: string; is_active: boolean };

export const operationsApi = {
  getContractorSnapshot: async () => {
    const [companiesResponse, sitesResponse, contractsResponse] = await Promise.all([
      apiClient.get<{ items: CompanyDto[]; total: number }>("/companies", { params: { limit: 100, offset: 0 } }),
      apiClient.get<{ items: SiteDto[]; total: number }>("/sites", { params: { limit: 100, offset: 0 } }),
      apiClient.get<{ items: ContractDto[]; total: number }>("/contracts", { params: { limit: 100, offset: 0 } })
    ]);
    return {
      companies: companiesResponse.data.items ?? [],
      sites: sitesResponse.data.items ?? [],
      contracts: contractsResponse.data.items ?? []
    };
  },

  getReferenceSnapshot: async () => {
    const [npaResponse, ppeResponse, programsResponse, templatesResponse, briefingTemplates] = await Promise.all([
      apiClient.get<{ items: Array<{ id: string; code: string; title: string }> }>("/npa"),
      apiClient.get<{ items: PpeItemDto[]; total: number }>("/ppe/items", { params: { limit: 100, offset: 0 } }),
      apiClient.get<{ items: TrainingProgramDto[] }>("/training/programs"),
      apiClient.get<{ items: TemplateDto[]; total?: number }>("/templates", { params: { limit: 100, offset: 0 } }),
      briefingsApi.listTemplates()
    ]);
    return {
      npa: npaResponse.data.items ?? [],
      ppeItems: ppeResponse.data.items ?? [],
      programs: programsResponse.data.items ?? [],
      templates: templatesResponse.data.items ?? [],
      briefingTemplates
    };
  },

  getSettingsSnapshot: async () => {
    const [tenancyResponse, notificationsResponse, apiTokensResponse] = await Promise.all([
      apiClient.get<TenancyContextDto>("/tenancy/context"),
      apiClient.get<NotificationSettingsDto>("/notifications/settings/me"),
      apiClient.get<ApiTokenDto[]>("/api-tokens")
    ]);
    return {
      tenancy: tenancyResponse.data,
      notifications: notificationsResponse.data,
      apiTokens: apiTokensResponse.data ?? []
    };
  },

  getActivitiesSnapshot: async () => {
    const [tasksResponse, actions] = await Promise.all([
      apiClient.get<{ items: TaskDto[]; pagination: { total: number } }>("/tasks", { params: { page: 1, page_size: 100 } }),
      opsApi.getCorrectiveActions()
    ]);
    return {
      tasks: tasksResponse.data.items ?? [],
      correctiveActions: actions
    };
  },

  getMedicalSnapshot: async () => {
    const [examsResponse, personsResponse, tasksResponse] = await Promise.all([
      apiClient.get<{ items: MedicalExamDto[]; total: number }>("/medical/exams", { params: { limit: 100, offset: 0 } }),
      apiClient.get<{ items: PersonDto[]; total: number }>("/persons", { params: { page: 1, page_size: 100 } }),
      apiClient.get<{ items: TaskDto[]; pagination: { total: number } }>("/tasks", { params: { type: "medical_requirement", page: 1, page_size: 100 } })
    ]);
    return {
      exams: examsResponse.data.items ?? [],
      persons: personsResponse.data.items ?? [],
      tasks: tasksResponse.data.items ?? []
    };
  },

  getFireSafetySnapshot: async () => {
    const [sitesResponse, inspectionsResponse, tasksResponse] = await Promise.all([
      apiClient.get<{ items: SiteDto[]; total: number }>("/sites", { params: { limit: 100, offset: 0 } }),
      apiClient.get<{ items: InspectionDto[]; total: number }>("/inspections", { params: { limit: 100, offset: 0 } }),
      apiClient.get<{ items: TaskDto[]; pagination: { total: number } }>("/tasks", { params: { type: "inspection", page: 1, page_size: 100 } })
    ]);
    return {
      sites: sitesResponse.data.items ?? [],
      inspections: inspectionsResponse.data.items ?? [],
      tasks: tasksResponse.data.items ?? []
    };
  },

  getFireTrainingSnapshot: async () => {
    const [templates, journals, overdue, programsResponse] = await Promise.all([
      briefingsApi.listTemplates(),
      briefingsApi.listJournals(),
      briefingsApi.listOverdue(),
      apiClient.get<{ items: TrainingProgramDto[] }>("/training/programs")
    ]);
    return {
      templates,
      journals,
      overdueEntries: overdue,
      programs: programsResponse.data.items ?? []
    };
  },

  getInspectionWorkspaceSnapshot: async () => {
    const [inspectionsResponse, prescriptions, tasksResponse, templates, packsResponse] = await Promise.all([
      apiClient.get<{ items: InspectionDto[]; total: number }>("/inspections", { params: { limit: 100, offset: 0 } }),
      opsApi.getPrescriptions(),
      apiClient.get<{ items: TaskDto[]; pagination: { total: number } }>("/tasks", { params: { type: "inspection", page: 1, page_size: 100 } }),
      apiClient.get<{ items: TemplateDto[]; total?: number }>("/templates", { params: { limit: 100, offset: 0 } }),
      apiClient.get<unknown[]>("/pack-runs").catch(() => ({ data: [] as unknown[] }))
    ]);
    return {
      inspections: inspectionsResponse.data.items ?? [],
      prescriptions,
      tasks: tasksResponse.data.items ?? [],
      templates: templates.data.items ?? [],
      packRuns: Array.isArray(packsResponse.data) ? packsResponse.data : []
    };
  },

  getAdminSnapshot: async () => {
    const [tenancyResponse, outboxResponse, webhookResponse, apiTokensResponse, auditResponse] = await Promise.all([
      apiClient.get<TenancyContextDto>("/tenancy/context"),
      apiClient.get<{ items: OutboxDto[]; total: number }>("/admin/outbox"),
      apiClient.get<WebhookEndpointDto[]>("/webhooks/endpoints"),
      apiClient.get<ApiTokenDto[]>("/api-tokens"),
      apiClient.get<{ items: Array<{ id: string; action: string; object_type: string; created_at: string }>; total: number }>("/audit")
    ]);
    return {
      tenancy: tenancyResponse.data,
      outbox: outboxResponse.data.items ?? [],
      webhooks: webhookResponse.data ?? [],
      apiTokens: apiTokensResponse.data ?? [],
      auditItems: auditResponse.data.items ?? []
    };
  }
};

export type FireTrainingSnapshot = Awaited<ReturnType<typeof operationsApi.getFireTrainingSnapshot>>;
export type InspectionWorkspaceSnapshot = Awaited<ReturnType<typeof operationsApi.getInspectionWorkspaceSnapshot>>;
export type AdminSnapshot = Awaited<ReturnType<typeof operationsApi.getAdminSnapshot>>;
export type MedicalSnapshot = Awaited<ReturnType<typeof operationsApi.getMedicalSnapshot>>;
export type SettingsSnapshot = Awaited<ReturnType<typeof operationsApi.getSettingsSnapshot>>;
export type ContractorSnapshot = Awaited<ReturnType<typeof operationsApi.getContractorSnapshot>>;
export type ReferenceSnapshot = Awaited<ReturnType<typeof operationsApi.getReferenceSnapshot>>;
export type ActivitiesSnapshot = Awaited<ReturnType<typeof operationsApi.getActivitiesSnapshot>>;
export type FireSafetySnapshot = Awaited<ReturnType<typeof operationsApi.getFireSafetySnapshot>>;
export type BriefingCollections = { templates: BriefingTemplateDto[]; journals: BriefingJournalDto[]; overdueEntries: BriefingEntryDto[] };
export type OperationalActionDto = CorrectiveActionDto;
export type InspectionRegistryDto = InspectionDto;
export type PrescriptionRegistryDto = PrescriptionDto;
