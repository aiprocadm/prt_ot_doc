export type ComplianceStatus = "valid" | "pending" | "expired" | "blocked";
export type IncidentSeverity = "low" | "medium" | "high" | "critical";
export type ExpiryStatus = "ok" | "due_soon" | "overdue" | "missing";
export type DocType =
  | "license"
  | "insurance"
  | "contract"
  | "sro"
  | "training_cert"
  | "medical_cert"
  | "access_permit"
  | "qualification"
  | "other";
export type DocScope = "company" | "employee";
export type AdmissionStatus = "ok" | "warning" | "blocked";

export interface ContractorRegistry {
  id: string;
  name: string;
  legal_name?: string | null;
  company_id?: string | null;
  inn?: string | null;
  status: string;
  contact_person?: string | null;
  contact_phone?: string | null;
}

export interface ContractorRegistryPage {
  items: ContractorRegistry[];
  total: number;
  roles?: string[];
}

export interface ContractorEmployee {
  id: string;
  contractor_id: string;
  full_name: string;
  position?: string | null;
  personnel_number?: string | null;
  access_status: ComplianceStatus;
  training_status: ComplianceStatus;
  medical_status: ComplianceStatus;
}

export interface ContractorEmployeePage {
  items: ContractorEmployee[];
  total: number;
}

export interface ContractorIncident {
  id: string;
  contractor_id: string;
  employee_id?: string | null;
  incident_type: string;
  severity: IncidentSeverity;
  status: string;
  occurred_at: string;
  description?: string | null;
}

export interface ContractorIncidentPage {
  items: ContractorIncident[];
  total: number;
}

export interface ContractorDocument {
  id: string;
  contractor_id: string;
  employee_id?: string | null;
  doc_type: DocType;
  title: string;
  number?: string | null;
  issuing_org?: string | null;
  issued_at?: string | null;
  valid_until?: string | null;
  file_id?: string | null;
  status: string;
  expiry_status: ExpiryStatus;
}

export interface ContractorDocumentPage {
  items: ContractorDocument[];
  total: number;
}

export interface ContractorDocumentRequirement {
  id: string;
  doc_type: DocType;
  scope: DocScope;
  mandatory: boolean;
}

export interface ContractorDocumentRequirementPage {
  items: ContractorDocumentRequirement[];
  total: number;
}

export interface ContractorComplianceSummary {
  contractor_id?: string | null;
  employees_total: number;
  admission: Record<string, number>;
  training: Record<string, number>;
  medical: Record<string, number>;
}

export interface AdmissionVerdict {
  employee_id: string;
  status: AdmissionStatus;
  violations: string[];
  warnings: string[];
}

export interface DocumentChecklistItem {
  doc_type: DocType;
  scope: DocScope;
  mandatory: boolean;
  status: ExpiryStatus;
  satisfied_by: { document_id: string; valid_until: string | null } | null;
}

export interface DocumentChecklist {
  employee_id: string;
  items: DocumentChecklistItem[];
}

export interface ContractorRegistryCreate {
  name: string;
  legal_name?: string | null;
  company_id?: string | null;
  inn?: string | null;
  contact_person?: string | null;
  contact_phone?: string | null;
}

export interface ContractorRegistryPatch {
  name?: string;
  legal_name?: string | null;
  company_id?: string | null;
  inn?: string | null;
  status?: string;
  contact_person?: string | null;
  contact_phone?: string | null;
}

export interface ContractorEmployeeCreate {
  contractor_id: string;
  full_name: string;
  position?: string | null;
  personnel_number?: string | null;
  access_status?: ComplianceStatus;
  training_status?: ComplianceStatus;
  medical_status?: ComplianceStatus;
}

export interface ContractorEmployeePatch {
  position?: string | null;
  access_status?: ComplianceStatus;
  training_status?: ComplianceStatus;
  medical_status?: ComplianceStatus;
}

export interface ContractorIncidentCreate {
  contractor_id: string;
  employee_id?: string | null;
  incident_type: string;
  severity: IncidentSeverity;
  status?: string;
  occurred_at: string;
  description?: string | null;
}

export interface ContractorDocumentCreate {
  contractor_id: string;
  employee_id?: string | null;
  doc_type: DocType;
  title: string;
  number?: string | null;
  issuing_org?: string | null;
  issued_at?: string | null;
  valid_until?: string | null;
  file_id?: string | null;
}

export interface ContractorDocumentPatch {
  doc_type?: DocType;
  title?: string;
  number?: string | null;
  issuing_org?: string | null;
  issued_at?: string | null;
  valid_until?: string | null;
  file_id?: string | null;
  status?: string;
}

export interface DocumentRequirementCreate {
  doc_type: DocType;
  scope: DocScope;
  mandatory: boolean;
}
