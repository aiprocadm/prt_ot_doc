import { apiClient } from "@/api/client";
import type { ApiError } from "@/types/dto/common";
import type {
  AdmissionVerdict,
  ContractorComplianceSummary,
  ContractorDocument,
  ContractorDocumentCreate,
  ContractorDocumentPage,
  ContractorDocumentPatch,
  ContractorDocumentRequirement,
  ContractorDocumentRequirementPage,
  ContractorEmployee,
  ContractorEmployeeCreate,
  ContractorEmployeePage,
  ContractorEmployeePatch,
  ContractorIncident,
  ContractorIncidentCreate,
  ContractorIncidentPage,
  ContractorRegistry,
  ContractorRegistryCreate,
  ContractorRegistryPage,
  ContractorRegistryPatch,
  DocScope,
  DocType,
  DocumentChecklist,
  DocumentRequirementCreate
} from "@/types/dto/contractors";

const BASE = "/contractors";

export const isFeatureDisabledError = (error: unknown): boolean => {
  const e = error as Partial<ApiError> | null;
  return Boolean(e && e.status === 404 && /feature is not enabled/i.test(e.message ?? ""));
};

export type DocumentListParams = {
  contractor_id?: string;
  employee_id?: string;
  doc_type?: DocType;
  status?: string;
};

export const contractorsApi = {
  // ── Registry ──────────────────────────────────────────────────────────
  async listRegistry(params: { limit?: number; offset?: number } = {}): Promise<ContractorRegistryPage> {
    const { data } = await apiClient.get<ContractorRegistryPage>(`${BASE}/registry`, {
      params: { limit: 100, offset: 0, ...params }
    });
    return { items: data.items ?? [], total: data.total ?? 0, roles: data.roles };
  },
  async getRegistry(id: string): Promise<ContractorRegistry> {
    return (await apiClient.get<ContractorRegistry>(`${BASE}/registry/${id}`)).data;
  },
  async createRegistry(payload: ContractorRegistryCreate): Promise<ContractorRegistry> {
    return (await apiClient.post<ContractorRegistry>(`${BASE}/registry`, payload)).data;
  },
  async updateRegistry(id: string, payload: ContractorRegistryPatch): Promise<ContractorRegistry> {
    return (await apiClient.patch<ContractorRegistry>(`${BASE}/registry/${id}`, payload)).data;
  },
  async archiveRegistry(id: string): Promise<void> {
    await apiClient.delete(`${BASE}/registry/${id}`);
  },

  // ── Employees ─────────────────────────────────────────────────────────
  async listEmployees(params: { contractor_id?: string } = {}): Promise<ContractorEmployeePage> {
    const { data } = await apiClient.get<ContractorEmployeePage>(`${BASE}/employees`, { params });
    return { items: data.items ?? [], total: data.total ?? 0 };
  },
  async createEmployee(payload: ContractorEmployeeCreate): Promise<ContractorEmployee> {
    return (await apiClient.post<ContractorEmployee>(`${BASE}/employees`, payload)).data;
  },
  async updateEmployee(id: string, payload: ContractorEmployeePatch): Promise<ContractorEmployee> {
    return (await apiClient.patch<ContractorEmployee>(`${BASE}/employees/${id}`, payload)).data;
  },

  // ── Admission ─────────────────────────────────────────────────────────
  async getEmployeeReadiness(id: string): Promise<AdmissionVerdict> {
    return (await apiClient.get<AdmissionVerdict>(`${BASE}/employees/${id}/readiness`)).data;
  },
  async getEmployeeChecklist(id: string): Promise<DocumentChecklist> {
    return (await apiClient.get<DocumentChecklist>(`${BASE}/employees/${id}/document-checklist`)).data;
  },
  async admitEmployee(id: string): Promise<AdmissionVerdict> {
    return (await apiClient.post<AdmissionVerdict>(`${BASE}/employees/${id}/admit`)).data;
  },

  // ── Incidents ─────────────────────────────────────────────────────────
  async listIncidents(params: { contractor_id?: string } = {}): Promise<ContractorIncidentPage> {
    const { data } = await apiClient.get<ContractorIncidentPage>(`${BASE}/incidents`, { params });
    return { items: data.items ?? [], total: data.total ?? 0 };
  },
  async createIncident(payload: ContractorIncidentCreate): Promise<ContractorIncident> {
    return (await apiClient.post<ContractorIncident>(`${BASE}/incidents`, payload)).data;
  },

  // ── Compliance ────────────────────────────────────────────────────────
  async getComplianceSummary(params: { contractor_id?: string } = {}): Promise<ContractorComplianceSummary> {
    return (await apiClient.get<ContractorComplianceSummary>(`${BASE}/compliance-summary`, { params })).data;
  },

  // ── Documents ─────────────────────────────────────────────────────────
  async listDocuments(params: DocumentListParams = {}): Promise<ContractorDocumentPage> {
    const { data } = await apiClient.get<ContractorDocumentPage>(`${BASE}/documents`, { params });
    return { items: data.items ?? [], total: data.total ?? 0 };
  },
  async listExpiringDocuments(params: { contractor_id?: string } = {}): Promise<ContractorDocumentPage> {
    const { data } = await apiClient.get<ContractorDocumentPage>(`${BASE}/documents/expiring`, { params });
    return { items: data.items ?? [], total: data.total ?? 0 };
  },
  async getDocument(id: string): Promise<ContractorDocument> {
    return (await apiClient.get<ContractorDocument>(`${BASE}/documents/${id}`)).data;
  },
  async createDocument(payload: ContractorDocumentCreate): Promise<ContractorDocument> {
    return (await apiClient.post<ContractorDocument>(`${BASE}/documents`, payload)).data;
  },
  async updateDocument(id: string, payload: ContractorDocumentPatch): Promise<ContractorDocument> {
    return (await apiClient.patch<ContractorDocument>(`${BASE}/documents/${id}`, payload)).data;
  },
  async archiveDocument(id: string): Promise<void> {
    await apiClient.delete(`${BASE}/documents/${id}`);
  },

  // ── Document requirements (tenant policy) ─────────────────────────────
  async listRequirements(): Promise<ContractorDocumentRequirementPage> {
    const { data } = await apiClient.get<ContractorDocumentRequirementPage>(`${BASE}/document-requirements`);
    return { items: data.items ?? [], total: data.total ?? 0 };
  },
  async createRequirement(payload: DocumentRequirementCreate): Promise<ContractorDocumentRequirement> {
    return (await apiClient.post<ContractorDocumentRequirement>(`${BASE}/document-requirements`, payload)).data;
  },
  async deleteRequirement(id: string): Promise<void> {
    await apiClient.delete(`${BASE}/document-requirements/${id}`);
  }
};

export type { DocScope };
