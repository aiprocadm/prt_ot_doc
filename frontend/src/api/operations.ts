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



export type ContractorRegistryDto = {
  id: string;
  name: string;
  status: string;
  company_id?: string | null;
  contact_person?: string | null;
  contact_phone?: string | null;
};

export type ContractorEmployeeDto = {
  id: string;
  contractor_id: string;
  full_name: string;
  position?: string | null;
  access_status: string;
  training_status: string;
  medical_status: string;
};

export type ContractorIncidentDto = {
  id: string;
  contractor_id: string;
  employee_id?: string | null;
  incident_type: string;
  severity: string;
  status: string;
  occurred_at: string;
};

export type ContractorComplianceSummaryDto = {
  contractor_id?: string | null;
  employees_total: number;
  admission: Record<string, number>;
  training: Record<string, number>;
  medical: Record<string, number>;
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
export type IntegrationReadinessDto = {
  tenant_id: string;
  providers: Array<{
    provider: string;
    adapter?: string;
    configured?: boolean;
    provider_mode?: string;
    provider_production_ready?: boolean;
    health_status?: string;
    provider_warning?: string;
  }>;
  summary: {
    configured_total: number;
    production_ready_total: number;
    non_production_total: number;
    disabled_total: number;
  };
  webhooks: {
    configured_total: number;
    enabled_total: number;
    delivery_total: number;
    delivery_sent_total: number;
    delivery_failed_total: number;
  };
  notes: string[];
};

export type WorkspaceAttentionDto = {
  generated_at: string;
  summary: {
    overdue_tasks: number;
    due_soon_tasks: number;
    overdue_deadlines: number;
    pending_sync_batches: number;
    failed_sync_batches: number;
    readiness_blockers: number;
  };
  items: Array<{
    id: string;
    title: string;
    severity: string;
    status: string;
    reason: string;
  }>;
  blockers: Array<{
    code: string;
    title: string;
    severity: string;
    count: number;
    reason: string;
    action_hint: string;
  }>;
  recommendations: string[];
};

export type WorkspaceTaskInboxDto = {
  total: number;
  overdue: number;
  items: Array<{
    id: string;
    title: string;
    status: string;
    priority: string;
    overdue: boolean;
  }>;
};

export type ProviderStatusDto = {
  generated_at: string;
  production_ready: boolean;
  providers: Array<{
    name: string;
    adapter: string;
    mode: string;
    production_ready: boolean;
    warning?: string | null;
  }>;
  blocking_for_golive: string[];
};

export type TenantHealthDto = {
  generated_at: string;
  score: number;
  grade: string;
  failed_jobs_last24h: number;
  outbox_pending: number;
  outbox_failed: number;
  outbox_events_poisoned: number;
  non_production_providers: number;
  blocking_providers: string[];
  recommendations: string[];
};

export type RoleWorkspaceSummaryDto = {
  generated_at: string;
  role: string;
  open_tasks: number;
  overdue_tasks: number;
  open_incidents: number;
  open_inspections: number;
  overdue_training: number;
  expired_ppe: number;
  overdue_deadlines: number;
  recommendations: string[];
};

export const operationsApi = {
  getContractorSnapshot: async () => {
    const [registryResponse, employeesResponse, incidentsResponse, summaryResponse] = await Promise.all([
      apiClient.get<{ items: ContractorRegistryDto[]; total: number }>("/contractors/registry", { params: { limit: 100, offset: 0 } }),
      apiClient.get<{ items: ContractorEmployeeDto[]; total: number }>("/contractors/employees"),
      apiClient.get<{ items: ContractorIncidentDto[]; total: number }>("/contractors/incidents"),
      apiClient.get<ContractorComplianceSummaryDto>("/contractors/compliance-summary")
    ]);
    return {
      companies: registryResponse.data.items ?? [],
      sites: [],
      contracts: [],
      employees: employeesResponse.data.items ?? [],
      incidents: incidentsResponse.data.items ?? [],
      complianceSummary: summaryResponse.data
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
      apiClient.get<TenancyContextDto>("/tenancy/context").catch(() => ({ data: { tenant: { id: "", slug: "" } } as TenancyContextDto })),
      apiClient.get<{ items: OutboxDto[]; total: number }>("/admin/outbox").catch(() => ({ data: { items: [], total: 0 } })),
      apiClient.get<WebhookEndpointDto[]>("/webhooks/endpoints").catch(() => ({ data: [] as WebhookEndpointDto[] })),
      apiClient.get<ApiTokenDto[]>("/api-tokens").catch(() => ({ data: [] as ApiTokenDto[] })),
      apiClient
        .get<{ items: Array<{ id: string; action: string; object_type: string; created_at: string }>; total: number }>("/audit")
        .catch(() => ({ data: { items: [], total: 0 } }))
    ]);

    const [integrationReadinessResponse, workspaceAttentionResponse, taskInboxResponse, providerStatusResponse, tenantHealthResponse, roleSummaryResponse] = await Promise.all([
      apiClient
        .get<IntegrationReadinessDto>("/integrations/readiness")
        .then((response) => response.data)
        .catch(() => null),
      apiClient
        .get<WorkspaceAttentionDto>("/workspace/attention", { params: { limit: 20 } })
        .then((response) => response.data)
        .catch(() => null),
      apiClient
        .get<WorkspaceTaskInboxDto>("/workspace/task-inbox", { params: { limit: 20, offset: 0 } })
        .then((response) => response.data)
        .catch(() => null),
      apiClient
        .get<ProviderStatusDto>("/admin/provider-status")
        .then((response) => response.data)
        .catch(() => null),
      apiClient
        .get<TenantHealthDto>("/admin/tenant-health")
        .then((response) => response.data)
        .catch(() => null),
      apiClient
        .get<RoleWorkspaceSummaryDto>("/workspace/role-summary")
        .then((response) => response.data)
        .catch(() => null)
    ]);

    return {
      tenancy: tenancyResponse.data,
      outbox: outboxResponse.data.items ?? [],
      webhooks: webhookResponse.data ?? [],
      apiTokens: apiTokensResponse.data ?? [],
      auditItems: auditResponse.data.items ?? [],
      integrationReadiness: integrationReadinessResponse,
      attention: workspaceAttentionResponse,
      taskInbox: taskInboxResponse,
      providerStatus: providerStatusResponse,
      tenantHealth: tenantHealthResponse,
      roleSummary: roleSummaryResponse
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
