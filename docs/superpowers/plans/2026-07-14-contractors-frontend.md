# Contractors Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire all 23 backend `/api/v1/contractors/*` endpoints into the React frontend — registry CRUD, a per-contractor detail page with tabs (Обзор / Сотрудники / Документы / Инциденты), the employee admission flow, and a tenant-level document-requirements policy.

**Architecture:** Typed `api/contractors.ts` client (mirrors `api/permits.ts`); the existing `/contractors` list page is refactored to tabs (Реестр / Истекающие документы / Требования к документам); a new `/contractors/:id` detail page (mirrors `WorkPermitDetailPage`) hosts per-contractor sub-resources. Write actions are gated by a new `CONTRACTOR_MANAGE` permission; the backend remains the true enforcer. Documents/admission/requirements are feature-flagged (`contractors`) — a 404 "feature is not enabled" renders a soft empty state, not an error.

**Tech Stack:** React 18, TypeScript, Vite, react-router-dom, axios (`apiClient`), Radix UI (`Dialog`, `Tabs`), sonner (toasts), TanStack Table (`RegistryTable`), Vitest + @testing-library/react.

**Reference files (read before starting):**
- Spec: `docs/superpowers/specs/2026-07-14-contractors-frontend-design.md`
- Backend router: `backend/app/api/routes/contractors.py`
- API client conventions: `frontend/src/api/permits.ts`, `frontend/src/api/incidents.ts`
- Dialog pattern: `frontend/src/features/permits/PermitFormDialog.tsx`
- List page pattern: `frontend/src/pages/permits/PermitsPage.tsx`
- Detail page pattern: `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`
- Test pattern: `frontend/src/pages/medical/MedicalPage.test.tsx`

**Backend enum values (verified from source):**
- `ComplianceStatus`: `valid | pending | expired | blocked`
- `IncidentSeverity`: `low | medium | high | critical`
- expiry `status` (`ContingentItemStatus`): `ok | due_soon | overdue | missing`
- `DocType`: `license | insurance | contract | sro | training_cert | medical_cert | access_permit | qualification | other`
- document requirement `scope`: `company | employee`

**Error contract (verified from `backend/app/api/error_handlers.py`):** caught errors are the normalized `ApiError` (`{status, message, code?, type?, details?, field_errors?}`). Notable cases:
- Admit blocked → `status: 409`, `code: "requirements_not_met"`, `details: { details: [{ employee_id, violations: string[] }] }`.
- Feature disabled → `status: 404`, `message: "Contractors feature is not enabled for this tenant"`.
- Requirement duplicate → `status: 409`, `code: "requirement_exists"`.
- Document employee/contractor mismatch → `status: 422`.

**Verification note:** documents/admission/requirements return 404 unless the demo tenant has the `contractors` feature flag enabled. Confirm/enable it before browser verification (Task 12).

**Commit discipline:** the working tree is shared across sessions — always `git add -- <explicit paths>` (never `git add -A`) and commit immediately after each task. Branch is already `feat/contractors-frontend`.

---

## Task 1: DTOs and vocab (labels/options)

**Files:**
- Create: `frontend/src/types/dto/contractors.ts`
- Create: `frontend/src/pages/contractors/contractorsVocab.ts`

- [ ] **Step 1: Create the DTO module**

Create `frontend/src/types/dto/contractors.ts`:

```ts
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
```

- [ ] **Step 2: Create the vocab module**

Create `frontend/src/pages/contractors/contractorsVocab.ts`:

```ts
import type {
  AdmissionStatus,
  ComplianceStatus,
  DocScope,
  DocType,
  ExpiryStatus,
  IncidentSeverity
} from "@/types/dto/contractors";

export const COMPLIANCE_STATUS_LABELS: Record<ComplianceStatus, string> = {
  valid: "Действителен",
  pending: "Ожидает",
  expired: "Просрочен",
  blocked: "Заблокирован"
};

export const COMPLIANCE_STATUS_OPTIONS: ComplianceStatus[] = ["pending", "valid", "expired", "blocked"];

export const SEVERITY_LABELS: Record<IncidentSeverity, string> = {
  low: "Низкая",
  medium: "Средняя",
  high: "Высокая",
  critical: "Критическая"
};

export const SEVERITY_OPTIONS: IncidentSeverity[] = ["low", "medium", "high", "critical"];

export const DOC_TYPE_LABELS: Record<DocType, string> = {
  license: "Лицензия",
  insurance: "Страховка",
  contract: "Договор",
  sro: "СРО",
  training_cert: "Удостоверение об обучении",
  medical_cert: "Медицинское заключение",
  access_permit: "Наряд-допуск",
  qualification: "Квалификация",
  other: "Другое"
};

export const DOC_TYPE_OPTIONS: DocType[] = [
  "license",
  "insurance",
  "contract",
  "sro",
  "training_cert",
  "medical_cert",
  "access_permit",
  "qualification",
  "other"
];

export const SCOPE_LABELS: Record<DocScope, string> = {
  company: "На компанию",
  employee: "На сотрудника"
};

export const SCOPE_OPTIONS: DocScope[] = ["company", "employee"];

export const EXPIRY_LABELS: Record<ExpiryStatus, string> = {
  ok: "Действует",
  due_soon: "Истекает",
  overdue: "Просрочен",
  missing: "Отсутствует"
};

export const EXPIRY_BADGE_VARIANT: Record<ExpiryStatus, "default" | "secondary" | "destructive"> = {
  ok: "default",
  due_soon: "secondary",
  overdue: "destructive",
  missing: "secondary"
};

export const ADMISSION_STATUS_LABELS: Record<AdmissionStatus, string> = {
  ok: "Допущен",
  warning: "Допущен с замечаниями",
  blocked: "Не допущен"
};
```

- [ ] **Step 3: Typecheck**

Run: `npm --prefix frontend run typecheck`
Expected: PASS (no unused-symbol errors; these modules are imported by later tasks).

- [ ] **Step 4: Commit**

```bash
git add -- frontend/src/types/dto/contractors.ts frontend/src/pages/contractors/contractorsVocab.ts
git commit -m "feat(contractors): frontend DTOs and vocab for contractors domain"
```

---

## Task 2: API client `contractorsApi`

**Files:**
- Create: `frontend/src/api/contractors.ts`
- Test: `frontend/src/api/contractors.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/contractors.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";

import { apiClient } from "@/api/client";
import { contractorsApi, isFeatureDisabledError } from "@/api/contractors";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  }
}));

beforeEach(() => {
  vi.clearAllMocks();
  (apiClient.get as any).mockResolvedValue({ data: { items: [], total: 0 } });
  (apiClient.post as any).mockResolvedValue({ data: { id: "x" } });
  (apiClient.patch as any).mockResolvedValue({ data: { id: "x" } });
  (apiClient.delete as any).mockResolvedValue({ data: null });
});

describe("contractorsApi", () => {
  it("lists the registry with default paging", async () => {
    await contractorsApi.listRegistry();
    expect(apiClient.get).toHaveBeenCalledWith("/contractors/registry", {
      params: { limit: 100, offset: 0 }
    });
  });

  it("scopes employees by contractor_id", async () => {
    await contractorsApi.listEmployees({ contractor_id: "c1" });
    expect(apiClient.get).toHaveBeenCalledWith("/contractors/employees", {
      params: { contractor_id: "c1" }
    });
  });

  it("admits an employee via the admit endpoint", async () => {
    (apiClient.post as any).mockResolvedValue({ data: { employee_id: "e1", status: "ok", violations: [], warnings: [] } });
    const verdict = await contractorsApi.admitEmployee("e1");
    expect(apiClient.post).toHaveBeenCalledWith("/contractors/employees/e1/admit");
    expect(verdict.status).toBe("ok");
  });

  it("archives a document with the document id in the path", async () => {
    await contractorsApi.archiveDocument("d1");
    expect(apiClient.delete).toHaveBeenCalledWith("/contractors/documents/d1");
  });

  it("detects the feature-disabled 404", () => {
    expect(isFeatureDisabledError({ status: 404, message: "Contractors feature is not enabled for this tenant" })).toBe(true);
    expect(isFeatureDisabledError({ status: 404, message: "Document not found" })).toBe(false);
    expect(isFeatureDisabledError({ status: 500, message: "boom" })).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/api/contractors.test.ts`
Expected: FAIL — cannot resolve `@/api/contractors`.

- [ ] **Step 3: Implement the API client**

Create `frontend/src/api/contractors.ts`:

```ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/api/contractors.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/api/contractors.ts frontend/src/api/contractors.test.ts
git commit -m "feat(contractors): typed contractorsApi client + feature-flag helper"
```

---

## Task 3: Permission + routing wiring

**Files:**
- Modify: `frontend/src/permissions/permissions.ts:64`
- Modify: `frontend/src/router/pageRegistry.tsx:34`
- Modify: `frontend/src/router/routeGroups.tsx:28,181`

- [ ] **Step 1: Add the `CONTRACTOR_MANAGE` permission**

In `frontend/src/permissions/permissions.ts`, add after the `CONTRACTOR_VIEW` line (line 43):

```ts
  CONTRACTOR_VIEW: "contractor.view",
  CONTRACTOR_MANAGE: "contractor.manage",
```

(owner/admin/ot_pb_head already receive it via `ALL_PERMISSIONS` / the ot_pb_head filter — no `ROLE_PERMISSIONS` edits needed.)

- [ ] **Step 2: Register the detail page (lazy)**

In `frontend/src/router/pageRegistry.tsx`, add after the `ContractorsPage` export (line 34):

```ts
export const ContractorsPage = lazy(() => import("@/pages/contractors/ContractorsPage"));
export const ContractorDetailPage = lazy(() => import("@/pages/contractors/ContractorDetailPage"));
```

- [ ] **Step 3: Add the detail route**

In `frontend/src/router/routeGroups.tsx`, add `ContractorDetailPage` to the import block from `@/router/pageRegistry` (alongside `ContractorsPage`, line 28):

```ts
  ContractorsPage,
  ContractorDetailPage,
```

Then replace the CONTRACTOR route group (line 181):

```tsx
    {
      permission: PERMISSIONS.CONTRACTOR_VIEW,
      routes: [
        <Route key="/contractors" path="/contractors" element={<ContractorsPage />} />,
        <Route key="/contractors/:id" path="/contractors/:id" element={<ContractorDetailPage />} />
      ]
    },
```

- [ ] **Step 4: Typecheck**

Run: `npm --prefix frontend run typecheck`
Expected: FAIL — `Cannot find module '@/pages/contractors/ContractorDetailPage'` (created in Task 7). This is expected; do NOT create a stub. Verify the ONLY error is the missing ContractorDetailPage module.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/permissions/permissions.ts frontend/src/router/pageRegistry.tsx frontend/src/router/routeGroups.tsx
git commit -m "feat(contractors): CONTRACTOR_MANAGE permission + /contractors/:id route wiring"
```

---

## Task 4: `ContractorFormDialog` (registry create/edit)

**Files:**
- Create: `frontend/src/features/contractors/ContractorFormDialog.tsx`

- [ ] **Step 1: Implement the dialog**

Create `frontend/src/features/contractors/ContractorFormDialog.tsx`:

```tsx
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { contractorsApi } from "@/api/contractors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ContractorRegistry } from "@/types/dto/contractors";

interface Props {
  trigger: ReactNode;
  initialData?: ContractorRegistry;
  onSubmitted?: (contractor: ContractorRegistry) => void;
}

const emptyForm = { name: "", legal_name: "", inn: "", contact_person: "", contact_phone: "", status: "active" };

export const ContractorFormDialog = ({ trigger, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const isEdit = Boolean(initialData);

  useEffect(() => {
    if (!open) return;
    setForm(
      initialData
        ? {
            name: initialData.name,
            legal_name: initialData.legal_name ?? "",
            inn: initialData.inn ?? "",
            contact_person: initialData.contact_person ?? "",
            contact_phone: initialData.contact_phone ?? "",
            status: initialData.status ?? "active"
          }
        : emptyForm
    );
  }, [open, initialData]);

  const set = (key: keyof typeof form, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const onSubmit = async () => {
    if (!form.name.trim()) {
      toast.error("Укажите название контрагента");
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        name: form.name.trim(),
        legal_name: form.legal_name || null,
        inn: form.inn || null,
        contact_person: form.contact_person || null,
        contact_phone: form.contact_phone || null
      };
      const result = initialData
        ? await contractorsApi.updateRegistry(initialData.id, { ...payload, status: form.status })
        : await contractorsApi.createRegistry(payload);
      toast.success(isEdit ? "Контрагент обновлён" : "Контрагент создан");
      onSubmitted?.(result);
      setOpen(false);
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось сохранить контрагента");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать контрагента" : "Новый контрагент"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="c-name">Название</Label>
            <Input id="c-name" value={form.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="c-legal">Юр. наименование</Label>
              <Input id="c-legal" value={form.legal_name} onChange={(e) => set("legal_name", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-inn">ИНН</Label>
              <Input id="c-inn" value={form.inn} onChange={(e) => set("inn", e.target.value)} />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="c-contact">Контактное лицо</Label>
              <Input id="c-contact" value={form.contact_person} onChange={(e) => set("contact_person", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="c-phone">Телефон</Label>
              <Input id="c-phone" value={form.contact_phone} onChange={(e) => set("contact_phone", e.target.value)} />
            </div>
          </div>
          {isEdit ? (
            <div className="space-y-2">
              <Label htmlFor="c-status">Статус</Label>
              <select
                id="c-status"
                className="h-10 w-full rounded-md border px-3"
                value={form.status}
                onChange={(e) => set("status", e.target.value)}
              >
                <option value="active">Активен</option>
                <option value="suspended">Приостановлен</option>
                <option value="blocked">Заблокирован</option>
              </select>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button onClick={() => void onSubmit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

- [ ] **Step 2: Typecheck**

Run: `npm --prefix frontend run typecheck`
Expected: same single pre-existing error from Task 3 (missing ContractorDetailPage); no new errors in this file.

- [ ] **Step 3: Commit**

```bash
git add -- frontend/src/features/contractors/ContractorFormDialog.tsx
git commit -m "feat(contractors): ContractorFormDialog for registry create/edit"
```

---

## Task 5: `ContractorsPage` — Реестр tab (refactor to `contractorsApi`)

**Files:**
- Modify: `frontend/src/pages/contractors/ContractorsPage.tsx` (full rewrite)
- Test: `frontend/src/pages/contractors/ContractorsPage.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/contractors/ContractorsPage.test.tsx`:

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import ContractorsPage from "./ContractorsPage";
import { contractorsApi } from "@/api/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      listRegistry: vi.fn(),
      listEmployees: vi.fn(),
      listIncidents: vi.fn(),
      listExpiringDocuments: vi.fn(),
      listRequirements: vi.fn(),
      createRegistry: vi.fn(),
      createRequirement: vi.fn(),
      deleteRequirement: vi.fn()
    }
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function" ? (children as (v: boolean) => unknown)(true) : children
}));

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.listRegistry as any).mockResolvedValue({
    items: [{ id: "c1", name: "ООО Подрядчик", status: "active", company_id: null }],
    total: 1
  });
  (contractorsApi.listEmployees as any).mockResolvedValue({ items: [{ id: "e1", contractor_id: "c1" }], total: 1 });
  (contractorsApi.listIncidents as any).mockResolvedValue({ items: [], total: 0 });
  (contractorsApi.listExpiringDocuments as any).mockResolvedValue({ items: [], total: 0 });
  (contractorsApi.listRequirements as any).mockResolvedValue({ items: [], total: 0 });
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <ContractorsPage />
    </MemoryRouter>
  );

describe("ContractorsPage registry tab", () => {
  it("renders the registry from contractorsApi", async () => {
    renderPage();
    expect(await screen.findByText("ООО Подрядчик")).toBeInTheDocument();
  });

  it("creates a contractor via the dialog", async () => {
    (contractorsApi.createRegistry as any).mockResolvedValue({ id: "c2", name: "Новый", status: "active" });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Новый контрагент" }));
    fireEvent.change(await screen.findByLabelText("Название"), { target: { value: "Новый" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(contractorsApi.createRegistry).toHaveBeenCalledWith(expect.objectContaining({ name: "Новый" }))
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/pages/contractors/ContractorsPage.test.tsx`
Expected: FAIL — current page uses `operationsApi.getContractorSnapshot`, not `contractorsApi`; "Новый контрагент" button absent.

- [ ] **Step 3: Rewrite the page**

Replace the entire contents of `frontend/src/pages/contractors/ContractorsPage.tsx`:

```tsx
import { useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";

import { contractorsApi } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ContractorFormDialog } from "@/features/contractors/ContractorFormDialog";
import { ContractorExpiringTab } from "@/features/contractors/ContractorExpiringTab";
import { ContractorRequirementsTab } from "@/features/contractors/ContractorRequirementsTab";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ContractorRegistry } from "@/types/dto/contractors";

type RegistryData = {
  contractors: ContractorRegistry[];
  employeeCounts: Map<string, number>;
  incidentCounts: Map<string, number>;
  expiringTotal: number;
};

const ContractorsPage = () => {
  const loader = useCallback(async (): Promise<RegistryData> => {
    const [registry, employees, incidents, expiring] = await Promise.all([
      contractorsApi.listRegistry(),
      contractorsApi.listEmployees(),
      contractorsApi.listIncidents(),
      contractorsApi.listExpiringDocuments()
    ]);
    const employeeCounts = new Map<string, number>();
    employees.items.forEach((e) => employeeCounts.set(e.contractor_id, (employeeCounts.get(e.contractor_id) ?? 0) + 1));
    const incidentCounts = new Map<string, number>();
    incidents.items.forEach((i) => incidentCounts.set(i.contractor_id, (incidentCounts.get(i.contractor_id) ?? 0) + 1));
    return { contractors: registry.items, employeeCounts, incidentCounts, expiringTotal: expiring.total };
  }, []);

  const { data, loading, error, reload } = useAsyncResource<RegistryData>({
    loader,
    initialData: { contractors: [], employeeCounts: new Map(), incidentCounts: new Map(), expiringTotal: 0 },
    errorMessage: "Не удалось загрузить реестр подрядчиков"
  });

  const rows = useMemo(
    () =>
      data.contractors.map((c) => ({
        ...c,
        employeeCount: data.employeeCounts.get(c.id) ?? 0,
        incidentCount: data.incidentCounts.get(c.id) ?? 0
      })),
    [data]
  );

  const registry = useLocalRegistry({
    items: rows,
    match: (item, query) =>
      [item.name, item.status, item.inn, item.contact_person].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  const columns: ColumnDef<(typeof rows)[number], unknown>[] = [
    {
      accessorKey: "name",
      header: "Контрагент",
      cell: ({ row }) => (
        <Link to={`/contractors/${row.original.id}`} className="font-medium text-primary hover:underline">
          {row.original.name}
        </Link>
      )
    },
    { accessorKey: "status", header: "Статус", cell: ({ row }) => row.original.status || "—" },
    { accessorKey: "inn", header: "ИНН", cell: ({ row }) => row.original.inn || "—" },
    { accessorKey: "employeeCount", header: "Сотрудники", cell: ({ row }) => `${row.original.employeeCount} чел.` },
    { accessorKey: "incidentCount", header: "Инциденты", cell: ({ row }) => `${row.original.incidentCount} шт.` },
    {
      accessorKey: "contact_person",
      header: "Контакт",
      cell: ({ row }) => row.original.contact_person || row.original.contact_phone || "—"
    }
  ];

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Контрагенты и подрядчики"
        description="Реестр подрядчиков поверх backend `/contractors/*`: сотрудники, документы, допуски, инциденты."
        actions={
          <Can permission={PERMISSIONS.CONTRACTOR_MANAGE} fallback={<Button disabled>Новый контрагент</Button>}>
            <ContractorFormDialog trigger={<Button>Новый контрагент</Button>} onSubmitted={() => void reload()} />
          </Can>
        }
        stats={[
          { label: "Контрагентов", value: data.contractors.length },
          { label: "Сотрудников", value: [...data.employeeCounts.values()].reduce((a, b) => a + b, 0) },
          { label: "Инцидентов", value: [...data.incidentCounts.values()].reduce((a, b) => a + b, 0) },
          { label: "Истекающих документов", value: data.expiringTotal }
        ]}
      />

      <Tabs defaultValue="registry">
        <TabsList>
          <TabsTrigger value="registry">Реестр</TabsTrigger>
          <TabsTrigger value="expiring">Истекающие документы</TabsTrigger>
          <TabsTrigger value="requirements">Требования к документам</TabsTrigger>
        </TabsList>

        <TabsContent value="registry" className="space-y-3">
          <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
          {loading ? <LoadingScreen label="Загрузка подрядчиков" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState title="Подрядчики не найдены" description="Добавьте контрагента или измените поиск." />
          ) : null}
          {!loading && !error && registry.total > 0 ? (
            <RegistryTable
              columns={columns}
              data={registry.pagedItems}
              pageIndex={registry.pageIndex}
              pageSize={registry.pageSize}
              total={registry.total}
              onPageChange={registry.onPageChange}
              onPageSizeChange={registry.onPageSizeChange}
              onSearchChange={registry.onSearchChange}
              searchPlaceholder="Поиск по названию, ИНН, контакту"
              caption="Реестр подрядчиков"
            />
          ) : null}
        </TabsContent>

        <TabsContent value="expiring">
          <ContractorExpiringTab />
        </TabsContent>

        <TabsContent value="requirements">
          <ContractorRequirementsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ContractorsPage;
```

(`ContractorExpiringTab` and `ContractorRequirementsTab` are created in Task 6. The test for this task only exercises the Реестр tab and the create dialog; the two sibling tabs are lazy in content but imported — Task 6 must land for typecheck to pass. Run this task's test after Task 6, OR temporarily verify via the `registry` assertions only. To keep tasks independently runnable, do Task 6 immediately after Step 3 here, then run Step 4.)

- [ ] **Step 4: Run the test to verify it passes** (after Task 6 files exist)

Run: `npm --prefix frontend run test -- src/pages/contractors/ContractorsPage.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/pages/contractors/ContractorsPage.tsx frontend/src/pages/contractors/ContractorsPage.test.tsx
git commit -m "feat(contractors): registry tab on contractorsApi with create + detail links"
```

---

## Task 6: Требования + Истекающие tabs

**Files:**
- Create: `frontend/src/features/contractors/DocumentRequirementFormDialog.tsx`
- Create: `frontend/src/features/contractors/ContractorRequirementsTab.tsx`
- Create: `frontend/src/features/contractors/ContractorExpiringTab.tsx`

- [ ] **Step 1: Create the requirement dialog**

Create `frontend/src/features/contractors/DocumentRequirementFormDialog.tsx`:

```tsx
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { contractorsApi } from "@/api/contractors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { DOC_TYPE_LABELS, DOC_TYPE_OPTIONS, SCOPE_LABELS, SCOPE_OPTIONS } from "@/pages/contractors/contractorsVocab";
import type { DocScope, DocType } from "@/types/dto/contractors";

interface Props {
  trigger: ReactNode;
  onSubmitted?: () => void;
}

export const DocumentRequirementFormDialog = ({ trigger, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [docType, setDocType] = useState<DocType>("license");
  const [scope, setScope] = useState<DocScope>("company");
  const [mandatory, setMandatory] = useState(true);

  const onSubmit = async () => {
    setSubmitting(true);
    try {
      await contractorsApi.createRequirement({ doc_type: docType, scope, mandatory });
      toast.success("Требование добавлено");
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      const e = err as { status?: number; code?: string; message?: string };
      if (e.status === 409 || e.code === "requirement_exists") {
        toast.error("Требование для этого типа документа и области уже существует");
      } else {
        toast.error(e.message ?? "Не удалось добавить требование");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новое требование к документу</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="req-type">Тип документа</Label>
            <select
              id="req-type"
              className="h-10 w-full rounded-md border px-3"
              value={docType}
              onChange={(e) => setDocType(e.target.value as DocType)}
            >
              {DOC_TYPE_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {DOC_TYPE_LABELS[t]}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="req-scope">Область</Label>
            <select
              id="req-scope"
              className="h-10 w-full rounded-md border px-3"
              value={scope}
              onChange={(e) => setScope(e.target.value as DocScope)}
            >
              {SCOPE_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {SCOPE_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={mandatory} onChange={(e) => setMandatory(e.target.checked)} />
            Обязательный документ
          </label>
        </div>
        <DialogFooter>
          <Button onClick={() => void onSubmit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Добавить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

- [ ] **Step 2: Create the requirements tab**

Create `frontend/src/features/contractors/ContractorRequirementsTab.tsx`:

```tsx
import { useCallback } from "react";
import { toast } from "sonner";

import { contractorsApi, isFeatureDisabledError } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DocumentRequirementFormDialog } from "@/features/contractors/DocumentRequirementFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { DOC_TYPE_LABELS, SCOPE_LABELS } from "@/pages/contractors/contractorsVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ContractorDocumentRequirement } from "@/types/dto/contractors";

export const ContractorRequirementsTab = () => {
  const loader = useCallback(() => contractorsApi.listRequirements().then((p) => p.items), []);
  const { data, loading, error, reload } = useAsyncResource<ContractorDocumentRequirement[]>({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить требования"
  });

  const onDelete = async (id: string) => {
    if (!window.confirm("Удалить требование?")) return;
    try {
      await contractorsApi.deleteRequirement(id);
      toast.success("Требование удалено");
      void reload();
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось удалить требование");
    }
  };

  if (error && isFeatureDisabledError(error)) {
    return <EmptyState title="Функция недоступна" description="Требования к документам не включены для этого тенанта." />;
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
          <DocumentRequirementFormDialog trigger={<Button>Новое требование</Button>} onSubmitted={() => void reload()} />
        </Can>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка требований" /> : null}
      {!loading && !error && data.length === 0 ? (
        <EmptyState title="Требований нет" description="Добавьте требование к документам подрядчиков." />
      ) : null}
      {!loading && !error && data.length > 0 ? (
        <ul className="divide-y rounded-md border">
          {data.map((req) => (
            <li key={req.id} className="flex items-center justify-between gap-3 p-3">
              <div className="flex items-center gap-2 text-sm">
                <span className="font-medium">{DOC_TYPE_LABELS[req.doc_type] ?? req.doc_type}</span>
                <Badge variant="secondary">{SCOPE_LABELS[req.scope] ?? req.scope}</Badge>
                {req.mandatory ? <Badge>Обязательный</Badge> : <Badge variant="secondary">Необязательный</Badge>}
              </div>
              <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
                <Button variant="ghost" size="sm" onClick={() => void onDelete(req.id)}>
                  Удалить
                </Button>
              </Can>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};
```

- [ ] **Step 3: Create the expiring-documents tab**

Create `frontend/src/features/contractors/ContractorExpiringTab.tsx`:

```tsx
import { useCallback } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { contractorsApi, isFeatureDisabledError } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Badge } from "@/components/ui/badge";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { DOC_TYPE_LABELS, EXPIRY_BADGE_VARIANT, EXPIRY_LABELS } from "@/pages/contractors/contractorsVocab";
import { formatDate } from "@/utils/datetime";
import type { ContractorDocument } from "@/types/dto/contractors";

export const ContractorExpiringTab = () => {
  const loader = useCallback(() => contractorsApi.listExpiringDocuments().then((p) => p.items), []);
  const { data, loading, error, reload } = useAsyncResource<ContractorDocument[]>({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить истекающие документы"
  });

  const registry = useLocalRegistry({
    items: data,
    match: (item, query) => [item.title, item.number, item.doc_type].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  const columns: ColumnDef<ContractorDocument, unknown>[] = [
    { accessorKey: "title", header: "Документ" },
    { accessorKey: "doc_type", header: "Тип", cell: ({ row }) => DOC_TYPE_LABELS[row.original.doc_type] ?? row.original.doc_type },
    { accessorKey: "valid_until", header: "Действует до", cell: ({ row }) => formatDate(row.original.valid_until ?? "") || "—" },
    {
      accessorKey: "expiry_status",
      header: "Состояние",
      cell: ({ row }) => (
        <Badge variant={EXPIRY_BADGE_VARIANT[row.original.expiry_status]}>{EXPIRY_LABELS[row.original.expiry_status]}</Badge>
      )
    }
  ];

  if (error && isFeatureDisabledError(error)) {
    return <EmptyState title="Функция недоступна" description="Документы подрядчиков не включены для этого тенанта." />;
  }

  return (
    <div className="space-y-3">
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка документов" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState title="Нет истекающих документов" description="Все документы подрядчиков в порядке." />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={columns}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по документу"
          caption="Истекающие документы подрядчиков"
        />
      ) : null}
    </div>
  );
};
```

- [ ] **Step 4: Run the ContractorsPage test (now that siblings exist)**

Run: `npm --prefix frontend run test -- src/pages/contractors/ContractorsPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/features/contractors/DocumentRequirementFormDialog.tsx frontend/src/features/contractors/ContractorRequirementsTab.tsx frontend/src/features/contractors/ContractorExpiringTab.tsx
git commit -m "feat(contractors): document-requirements policy tab + tenant expiring-docs tab"
```

---

## Task 7: `ContractorDetailPage` shell — header + Обзор (compliance)

**Files:**
- Create: `frontend/src/pages/contractors/ContractorDetailPage.tsx`
- Test: `frontend/src/pages/contractors/ContractorDetailPage.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/contractors/ContractorDetailPage.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import ContractorDetailPage from "./ContractorDetailPage";
import { contractorsApi } from "@/api/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      getRegistry: vi.fn(),
      getComplianceSummary: vi.fn(),
      listEmployees: vi.fn(),
      listIncidents: vi.fn(),
      listDocuments: vi.fn()
    }
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function" ? (children as (v: boolean) => unknown)(true) : children
}));

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.getRegistry as any).mockResolvedValue({ id: "c1", name: "ООО Подрядчик", status: "active", inn: "7701" });
  (contractorsApi.getComplianceSummary as any).mockResolvedValue({
    employees_total: 3,
    admission: { valid: 2, pending: 1 },
    training: { valid: 3 },
    medical: { pending: 3 }
  });
  (contractorsApi.listEmployees as any).mockResolvedValue({ items: [], total: 0 });
  (contractorsApi.listIncidents as any).mockResolvedValue({ items: [], total: 0 });
  (contractorsApi.listDocuments as any).mockResolvedValue({ items: [], total: 0 });
});

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/contractors/c1"]}>
      <Routes>
        <Route path="/contractors/:id" element={<ContractorDetailPage />} />
      </Routes>
    </MemoryRouter>
  );

describe("ContractorDetailPage", () => {
  it("renders the header and compliance KPI", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: /ООО Подрядчик/ })).toBeInTheDocument();
    expect(await screen.findByText("Сотрудников: 3")).toBeInTheDocument();
  });

  it("shows all four tabs", async () => {
    renderPage();
    expect(await screen.findByRole("tab", { name: "Обзор" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Сотрудники" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Документы" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Инциденты" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/pages/contractors/ContractorDetailPage.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the detail page**

Create `frontend/src/pages/contractors/ContractorDetailPage.tsx`:

```tsx
import { useCallback } from "react";
import { Link, useParams } from "react-router-dom";

import { contractorsApi } from "@/api/contractors";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ContractorFormDialog } from "@/features/contractors/ContractorFormDialog";
import { ContractorEmployeesTab } from "@/features/contractors/ContractorEmployeesTab";
import { ContractorDocumentsTab } from "@/features/contractors/ContractorDocumentsTab";
import { ContractorIncidentsTab } from "@/features/contractors/ContractorIncidentsTab";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { COMPLIANCE_STATUS_LABELS } from "@/pages/contractors/contractorsVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ComplianceStatus, ContractorComplianceSummary, ContractorRegistry } from "@/types/dto/contractors";

type DetailData = { contractor: ContractorRegistry | null; compliance: ContractorComplianceSummary | null };

const ComplianceRow = ({ title, totals }: { title: string; totals: Record<string, number> }) => (
  <div className="rounded-md border p-3">
    <div className="mb-2 text-sm font-medium">{title}</div>
    <div className="flex flex-wrap gap-3 text-sm">
      {Object.entries(totals).length === 0 ? (
        <span className="text-muted-foreground">—</span>
      ) : (
        Object.entries(totals).map(([status, count]) => (
          <span key={status}>
            {COMPLIANCE_STATUS_LABELS[status as ComplianceStatus] ?? status}: <strong>{count}</strong>
          </span>
        ))
      )}
    </div>
  </div>
);

export default function ContractorDetailPage() {
  const { id = "" } = useParams();

  const loader = useCallback(async (): Promise<DetailData> => {
    const [contractor, compliance] = await Promise.all([
      contractorsApi.getRegistry(id),
      contractorsApi.getComplianceSummary({ contractor_id: id })
    ]);
    return { contractor, compliance };
  }, [id]);

  const { data, loading, error, reload } = useAsyncResource<DetailData>({
    loader,
    initialData: { contractor: null, compliance: null },
    errorMessage: "Не удалось загрузить подрядчика"
  });

  if (loading) return <LoadingScreen label="Загрузка подрядчика" />;
  if (error || !data.contractor) return <ErrorState error={error ?? undefined} onRetry={() => void reload()} />;

  const c = data.contractor;

  return (
    <div className="space-y-5">
      <Link to="/contractors" className="text-sm text-muted-foreground hover:underline">
        ← Подрядчики
      </Link>

      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium">{c.name}</h1>
          <p className="text-sm text-muted-foreground">
            Статус: {c.status || "—"}
            {c.inn ? ` · ИНН ${c.inn}` : ""}
            {c.contact_person ? ` · ${c.contact_person}` : ""}
            {c.contact_phone ? ` · ${c.contact_phone}` : ""}
          </p>
        </div>
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
          <ContractorFormDialog
            trigger={<Button variant="outline">Изменить</Button>}
            initialData={c}
            onSubmitted={() => void reload()}
          />
        </Can>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Обзор</TabsTrigger>
          <TabsTrigger value="employees">Сотрудники</TabsTrigger>
          <TabsTrigger value="documents">Документы</TabsTrigger>
          <TabsTrigger value="incidents">Инциденты</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-3">
          <p className="text-sm">Сотрудников: {data.compliance?.employees_total ?? 0}</p>
          <div className="grid gap-3 md:grid-cols-3">
            <ComplianceRow title="Допуск" totals={data.compliance?.admission ?? {}} />
            <ComplianceRow title="Обучение" totals={data.compliance?.training ?? {}} />
            <ComplianceRow title="Медосмотр" totals={data.compliance?.medical ?? {}} />
          </div>
        </TabsContent>

        <TabsContent value="employees">
          <ContractorEmployeesTab contractorId={c.id} onChanged={() => void reload()} />
        </TabsContent>

        <TabsContent value="documents">
          <ContractorDocumentsTab contractorId={c.id} />
        </TabsContent>

        <TabsContent value="incidents">
          <ContractorIncidentsTab contractorId={c.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

(Tabs `ContractorEmployeesTab`, `ContractorDocumentsTab`, `ContractorIncidentsTab` are created in Tasks 8–11. Do those before running Step 4 / typecheck.)

- [ ] **Step 4: Run the test to verify it passes** (after Tasks 8–11 files exist)

Run: `npm --prefix frontend run test -- src/pages/contractors/ContractorDetailPage.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/pages/contractors/ContractorDetailPage.tsx frontend/src/pages/contractors/ContractorDetailPage.test.tsx
git commit -m "feat(contractors): detail page shell with header, tabs, compliance overview"
```

---

## Task 8: Сотрудники tab + `ContractorEmployeeFormDialog`

**Files:**
- Create: `frontend/src/features/contractors/ContractorEmployeeFormDialog.tsx`
- Create: `frontend/src/features/contractors/ContractorEmployeesTab.tsx`
- Test: `frontend/src/features/contractors/ContractorEmployeesTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/contractors/ContractorEmployeesTab.test.tsx`:

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { ContractorEmployeesTab } from "./ContractorEmployeesTab";
import { contractorsApi } from "@/api/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      listEmployees: vi.fn(),
      createEmployee: vi.fn(),
      getEmployeeReadiness: vi.fn(),
      getEmployeeChecklist: vi.fn(),
      admitEmployee: vi.fn()
    }
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function" ? (children as (v: boolean) => unknown)(true) : children
}));

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.listEmployees as any).mockResolvedValue({
    items: [
      { id: "e1", contractor_id: "c1", full_name: "Сидоров С.С.", position: "Монтажник", access_status: "pending", training_status: "valid", medical_status: "valid" }
    ],
    total: 1
  });
  (contractorsApi.createEmployee as any).mockResolvedValue({ id: "e2" });
});

describe("ContractorEmployeesTab", () => {
  it("lists employees scoped by contractor", async () => {
    render(<ContractorEmployeesTab contractorId="c1" onChanged={() => undefined} />);
    expect(await screen.findByText("Сидоров С.С.")).toBeInTheDocument();
    expect(contractorsApi.listEmployees).toHaveBeenCalledWith({ contractor_id: "c1" });
  });

  it("creates an employee for the contractor", async () => {
    render(<ContractorEmployeesTab contractorId="c1" onChanged={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Добавить сотрудника" }));
    fireEvent.change(await screen.findByLabelText("ФИО"), { target: { value: "Новый Н.Н." } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(contractorsApi.createEmployee).toHaveBeenCalledWith(
        expect.objectContaining({ contractor_id: "c1", full_name: "Новый Н.Н." })
      )
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/features/contractors/ContractorEmployeesTab.test.tsx`
Expected: FAIL — modules do not exist.

- [ ] **Step 3: Create the employee dialog**

Create `frontend/src/features/contractors/ContractorEmployeeFormDialog.tsx`:

```tsx
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { contractorsApi } from "@/api/contractors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { COMPLIANCE_STATUS_LABELS, COMPLIANCE_STATUS_OPTIONS } from "@/pages/contractors/contractorsVocab";
import type { ComplianceStatus, ContractorEmployee } from "@/types/dto/contractors";

interface Props {
  trigger: ReactNode;
  contractorId: string;
  initialData?: ContractorEmployee;
  onSubmitted?: () => void;
}

const StatusSelect = ({
  id,
  label,
  value,
  onChange
}: {
  id: string;
  label: string;
  value: ComplianceStatus;
  onChange: (v: ComplianceStatus) => void;
}) => (
  <div className="space-y-2">
    <Label htmlFor={id}>{label}</Label>
    <select id={id} className="h-10 w-full rounded-md border px-3" value={value} onChange={(e) => onChange(e.target.value as ComplianceStatus)}>
      {COMPLIANCE_STATUS_OPTIONS.map((s) => (
        <option key={s} value={s}>
          {COMPLIANCE_STATUS_LABELS[s]}
        </option>
      ))}
    </select>
  </div>
);

export const ContractorEmployeeFormDialog = ({ trigger, contractorId, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const isEdit = Boolean(initialData);
  const [fullName, setFullName] = useState("");
  const [position, setPosition] = useState("");
  const [access, setAccess] = useState<ComplianceStatus>("pending");
  const [training, setTraining] = useState<ComplianceStatus>("pending");
  const [medical, setMedical] = useState<ComplianceStatus>("pending");

  useEffect(() => {
    if (!open) return;
    setFullName(initialData?.full_name ?? "");
    setPosition(initialData?.position ?? "");
    setAccess(initialData?.access_status ?? "pending");
    setTraining(initialData?.training_status ?? "pending");
    setMedical(initialData?.medical_status ?? "pending");
  }, [open, initialData]);

  const onSubmit = async () => {
    if (!isEdit && !fullName.trim()) {
      toast.error("Укажите ФИО сотрудника");
      return;
    }
    setSubmitting(true);
    try {
      if (initialData) {
        await contractorsApi.updateEmployee(initialData.id, {
          position: position || null,
          access_status: access,
          training_status: training,
          medical_status: medical
        });
      } else {
        await contractorsApi.createEmployee({
          contractor_id: contractorId,
          full_name: fullName.trim(),
          position: position || null,
          access_status: access,
          training_status: training,
          medical_status: medical
        });
      }
      toast.success(isEdit ? "Сотрудник обновлён" : "Сотрудник добавлен");
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось сохранить сотрудника");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать сотрудника" : "Новый сотрудник подрядчика"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {!isEdit ? (
            <div className="space-y-2">
              <Label htmlFor="emp-name">ФИО</Label>
              <Input id="emp-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="emp-position">Должность</Label>
            <Input id="emp-position" value={position} onChange={(e) => setPosition(e.target.value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <StatusSelect id="emp-access" label="Допуск" value={access} onChange={setAccess} />
            <StatusSelect id="emp-training" label="Обучение" value={training} onChange={setTraining} />
            <StatusSelect id="emp-medical" label="Медосмотр" value={medical} onChange={setMedical} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => void onSubmit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

- [ ] **Step 4: Create the employees tab**

Create `frontend/src/features/contractors/ContractorEmployeesTab.tsx`:

```tsx
import { useCallback } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { contractorsApi } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Can } from "@/components/permissions/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ContractorEmployeeFormDialog } from "@/features/contractors/ContractorEmployeeFormDialog";
import { EmployeeAdmissionDialog } from "@/features/contractors/EmployeeAdmissionDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { COMPLIANCE_STATUS_LABELS } from "@/pages/contractors/contractorsVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type { ComplianceStatus, ContractorEmployee } from "@/types/dto/contractors";

const statusBadgeVariant = (s: ComplianceStatus): "default" | "secondary" | "destructive" =>
  s === "valid" ? "default" : s === "blocked" || s === "expired" ? "destructive" : "secondary";

const StatusCell = ({ value }: { value: ComplianceStatus }) => (
  <Badge variant={statusBadgeVariant(value)}>{COMPLIANCE_STATUS_LABELS[value] ?? value}</Badge>
);

export const ContractorEmployeesTab = ({ contractorId, onChanged }: { contractorId: string; onChanged?: () => void }) => {
  const loader = useCallback(() => contractorsApi.listEmployees({ contractor_id: contractorId }).then((p) => p.items), [contractorId]);
  const { data, loading, error, reload } = useAsyncResource<ContractorEmployee[]>({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить сотрудников"
  });

  const refresh = () => {
    void reload();
    onChanged?.();
  };

  const registry = useLocalRegistry({
    items: data,
    match: (item, query) => [item.full_name, item.position].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  const columns: ColumnDef<ContractorEmployee, unknown>[] = [
    { accessorKey: "full_name", header: "ФИО" },
    { accessorKey: "position", header: "Должность", cell: ({ row }) => row.original.position || "—" },
    { accessorKey: "access_status", header: "Допуск", cell: ({ row }) => <StatusCell value={row.original.access_status} /> },
    { accessorKey: "training_status", header: "Обучение", cell: ({ row }) => <StatusCell value={row.original.training_status} /> },
    { accessorKey: "medical_status", header: "Медосмотр", cell: ({ row }) => <StatusCell value={row.original.medical_status} /> },
    {
      id: "actions",
      header: "Действия",
      cell: ({ row }) => (
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE} fallback={<span className="text-muted-foreground">—</span>}>
          <div className="flex gap-2">
            <ContractorEmployeeFormDialog
              trigger={<Button variant="ghost" size="sm">Изменить</Button>}
              contractorId={contractorId}
              initialData={row.original}
              onSubmitted={refresh}
            />
            <EmployeeAdmissionDialog
              employee={row.original}
              trigger={<Button variant="ghost" size="sm">Допуск</Button>}
              onAdmitted={refresh}
            />
          </div>
        </Can>
      )
    }
  ];

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
          <ContractorEmployeeFormDialog
            trigger={<Button>Добавить сотрудника</Button>}
            contractorId={contractorId}
            onSubmitted={refresh}
          />
        </Can>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка сотрудников" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState title="Сотрудников нет" description="Добавьте сотрудника подрядчика." />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={columns}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по ФИО, должности"
          caption="Сотрудники подрядчика"
        />
      ) : null}
    </div>
  );
};
```

- [ ] **Step 5: Run test to verify it passes** (after Task 9 creates `EmployeeAdmissionDialog`)

Run: `npm --prefix frontend run test -- src/features/contractors/ContractorEmployeesTab.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add -- frontend/src/features/contractors/ContractorEmployeeFormDialog.tsx frontend/src/features/contractors/ContractorEmployeesTab.tsx frontend/src/features/contractors/ContractorEmployeesTab.test.tsx
git commit -m "feat(contractors): employees tab with create/edit + admission entrypoint"
```

---

## Task 9: `EmployeeAdmissionDialog` (readiness + checklist + admit)

**Files:**
- Create: `frontend/src/features/contractors/EmployeeAdmissionDialog.tsx`
- Test: `frontend/src/features/contractors/EmployeeAdmissionDialog.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/contractors/EmployeeAdmissionDialog.test.tsx`:

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { EmployeeAdmissionDialog } from "./EmployeeAdmissionDialog";
import { contractorsApi } from "@/api/contractors";
import { Button } from "@/components/ui/button";
import type { ContractorEmployee } from "@/types/dto/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      getEmployeeReadiness: vi.fn(),
      getEmployeeChecklist: vi.fn(),
      admitEmployee: vi.fn()
    }
  };
});

const employee: ContractorEmployee = {
  id: "e1",
  contractor_id: "c1",
  full_name: "Сидоров С.С.",
  access_status: "pending",
  training_status: "valid",
  medical_status: "valid"
};

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.getEmployeeReadiness as any).mockResolvedValue({ employee_id: "e1", status: "warning", violations: [], warnings: ["Медосмотр истекает"] });
  (contractorsApi.getEmployeeChecklist as any).mockResolvedValue({
    employee_id: "e1",
    items: [{ doc_type: "medical_cert", scope: "employee", mandatory: true, status: "due_soon", satisfied_by: null }]
  });
});

const open = async () => {
  render(<EmployeeAdmissionDialog employee={employee} trigger={<Button>Допуск</Button>} onAdmitted={() => undefined} />);
  fireEvent.click(screen.getByRole("button", { name: "Допуск" }));
};

describe("EmployeeAdmissionDialog", () => {
  it("loads readiness and checklist on open", async () => {
    await open();
    await waitFor(() => expect(contractorsApi.getEmployeeReadiness).toHaveBeenCalledWith("e1"));
    expect(contractorsApi.getEmployeeChecklist).toHaveBeenCalledWith("e1");
    expect(await screen.findByText("Медосмотр истекает")).toBeInTheDocument();
  });

  it("admits successfully with a warning verdict", async () => {
    (contractorsApi.admitEmployee as any).mockResolvedValue({ employee_id: "e1", status: "warning", violations: [], warnings: ["ок с замечаниями"] });
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Допустить" }));
    await waitFor(() => expect(contractorsApi.admitEmployee).toHaveBeenCalledWith("e1"));
    expect(await screen.findByText(/Допущен с замечаниями/)).toBeInTheDocument();
  });

  it("shows violations when admit is blocked (409)", async () => {
    (contractorsApi.admitEmployee as any).mockRejectedValue({
      status: 409,
      code: "requirements_not_met",
      message: "not cleared",
      details: { details: [{ employee_id: "e1", violations: ["Нет лицензии", "Просрочен медосмотр"] }] }
    });
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Допустить" }));
    expect(await screen.findByText("Нет лицензии")).toBeInTheDocument();
    expect(screen.getByText("Просрочен медосмотр")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/features/contractors/EmployeeAdmissionDialog.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the admission dialog**

Create `frontend/src/features/contractors/EmployeeAdmissionDialog.tsx`:

```tsx
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { contractorsApi } from "@/api/contractors";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { ADMISSION_STATUS_LABELS, DOC_TYPE_LABELS, EXPIRY_BADGE_VARIANT, EXPIRY_LABELS } from "@/pages/contractors/contractorsVocab";
import type { AdmissionVerdict, ContractorEmployee, DocumentChecklistItem } from "@/types/dto/contractors";

interface Props {
  employee: ContractorEmployee;
  trigger: ReactNode;
  onAdmitted?: () => void;
}

const extractViolations = (err: unknown): string[] => {
  const details = (err as { details?: { details?: Array<{ violations?: unknown[] }> } })?.details;
  const entries = details?.details ?? [];
  const all = entries.flatMap((e) => e.violations ?? []);
  return all.map((v) => (typeof v === "string" ? v : JSON.stringify(v)));
};

export const EmployeeAdmissionDialog = ({ employee, trigger, onAdmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [readiness, setReadiness] = useState<AdmissionVerdict | null>(null);
  const [checklist, setChecklist] = useState<DocumentChecklistItem[]>([]);
  const [blockedViolations, setBlockedViolations] = useState<string[]>([]);
  const [verdict, setVerdict] = useState<AdmissionVerdict | null>(null);

  useEffect(() => {
    if (!open) return;
    setBlockedViolations([]);
    setVerdict(null);
    setLoading(true);
    Promise.all([contractorsApi.getEmployeeReadiness(employee.id), contractorsApi.getEmployeeChecklist(employee.id)])
      .then(([r, c]) => {
        setReadiness(r);
        setChecklist(c.items ?? []);
      })
      .catch((err) => toast.error((err as { message?: string })?.message ?? "Не удалось загрузить готовность"))
      .finally(() => setLoading(false));
  }, [open, employee.id]);

  const onAdmit = async () => {
    setSubmitting(true);
    setBlockedViolations([]);
    try {
      const result = await contractorsApi.admitEmployee(employee.id);
      setVerdict(result);
      toast.success(ADMISSION_STATUS_LABELS[result.status] ?? "Допущен");
      onAdmitted?.();
    } catch (err) {
      const e = err as { status?: number; code?: string; message?: string };
      if (e.status === 409 || e.code === "requirements_not_met") {
        const violations = extractViolations(err);
        setBlockedViolations(violations.length ? violations : ["Не выполнены требования допуска"]);
      } else if (e.status === 404) {
        toast.error("Сотрудник не найден");
        setOpen(false);
      } else {
        toast.error(e.message ?? "Не удалось выполнить допуск");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Допуск: {employee.full_name}</DialogTitle>
        </DialogHeader>

        {loading ? <p className="text-sm text-muted-foreground">Загрузка готовности...</p> : null}

        {!loading && readiness ? (
          <div className="space-y-1 text-sm">
            <div>
              Готовность:{" "}
              <Badge variant={readiness.status === "ok" ? "default" : readiness.status === "blocked" ? "destructive" : "secondary"}>
                {ADMISSION_STATUS_LABELS[readiness.status] ?? readiness.status}
              </Badge>
            </div>
            {readiness.warnings.map((w) => (
              <p key={w} className="text-yellow-700">
                {w}
              </p>
            ))}
            {readiness.violations.map((v) => (
              <p key={v} className="text-destructive">
                {v}
              </p>
            ))}
          </div>
        ) : null}

        {!loading ? (
          <div className="space-y-2">
            <div className="text-sm font-medium">Документы по требованиям</div>
            {checklist.length === 0 ? (
              <p className="text-sm text-muted-foreground">Требования к документам не настроены.</p>
            ) : (
              <ul className="divide-y rounded-md border text-sm">
                {checklist.map((item) => (
                  <li key={`${item.doc_type}-${item.scope}`} className="flex items-center justify-between gap-2 p-2">
                    <span>
                      {DOC_TYPE_LABELS[item.doc_type] ?? item.doc_type}
                      {item.mandatory ? " *" : ""}
                    </span>
                    <Badge variant={EXPIRY_BADGE_VARIANT[item.status]}>{EXPIRY_LABELS[item.status]}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}

        {blockedViolations.length > 0 ? (
          <div role="alert" className="rounded-md border border-destructive bg-destructive/10 p-2 text-sm">
            <div className="mb-1 font-medium text-destructive">Допуск невозможен:</div>
            <ul className="list-inside list-disc">
              {blockedViolations.map((v) => (
                <li key={v}>{v}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {verdict ? <p className="text-sm text-green-700">{ADMISSION_STATUS_LABELS[verdict.status]}</p> : null}

        <DialogFooter>
          <Button onClick={() => void onAdmit()} disabled={submitting || loading}>
            {submitting ? "Проверка..." : "Допустить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/features/contractors/EmployeeAdmissionDialog.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add -- frontend/src/features/contractors/EmployeeAdmissionDialog.tsx frontend/src/features/contractors/EmployeeAdmissionDialog.test.tsx
git commit -m "feat(contractors): employee admission dialog (readiness/checklist/admit, 409+warning handling)"
```

---

## Task 10: Документы tab + `ContractorDocumentFormDialog`

**Files:**
- Create: `frontend/src/features/contractors/ContractorDocumentFormDialog.tsx`
- Create: `frontend/src/features/contractors/ContractorDocumentsTab.tsx`
- Test: `frontend/src/features/contractors/ContractorDocumentsTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/contractors/ContractorDocumentsTab.test.tsx`:

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { ContractorDocumentsTab } from "./ContractorDocumentsTab";
import { contractorsApi } from "@/api/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      listDocuments: vi.fn(),
      createDocument: vi.fn(),
      archiveDocument: vi.fn()
    }
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function" ? (children as (v: boolean) => unknown)(true) : children
}));

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.listDocuments as any).mockResolvedValue({
    items: [{ id: "d1", contractor_id: "c1", doc_type: "license", title: "Лицензия №1", status: "active", expiry_status: "ok" }],
    total: 1
  });
  (contractorsApi.createDocument as any).mockResolvedValue({ id: "d2" });
});

describe("ContractorDocumentsTab", () => {
  it("lists documents scoped by contractor", async () => {
    render(<ContractorDocumentsTab contractorId="c1" />);
    expect(await screen.findByText("Лицензия №1")).toBeInTheDocument();
    expect(contractorsApi.listDocuments).toHaveBeenCalledWith(expect.objectContaining({ contractor_id: "c1" }));
  });

  it("renders a soft state when the feature is disabled", async () => {
    (contractorsApi.listDocuments as any).mockRejectedValue({ status: 404, message: "Contractors feature is not enabled for this tenant" });
    render(<ContractorDocumentsTab contractorId="c1" />);
    expect(await screen.findByText(/Функция недоступна/)).toBeInTheDocument();
  });

  it("creates a document for the contractor", async () => {
    render(<ContractorDocumentsTab contractorId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Добавить документ" }));
    fireEvent.change(await screen.findByLabelText("Название"), { target: { value: "Новый документ" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(contractorsApi.createDocument).toHaveBeenCalledWith(
        expect.objectContaining({ contractor_id: "c1", title: "Новый документ", doc_type: "license" })
      )
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/features/contractors/ContractorDocumentsTab.test.tsx`
Expected: FAIL — modules do not exist.

- [ ] **Step 3: Create the document dialog**

Create `frontend/src/features/contractors/ContractorDocumentFormDialog.tsx`:

```tsx
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { contractorsApi } from "@/api/contractors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DOC_TYPE_LABELS, DOC_TYPE_OPTIONS } from "@/pages/contractors/contractorsVocab";
import type { ContractorDocument, ContractorEmployee, DocType } from "@/types/dto/contractors";

interface Props {
  trigger: ReactNode;
  contractorId: string;
  employees: ContractorEmployee[];
  initialData?: ContractorDocument;
  onSubmitted?: () => void;
}

export const ContractorDocumentFormDialog = ({ trigger, contractorId, employees, initialData, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const isEdit = Boolean(initialData);
  const [docType, setDocType] = useState<DocType>("license");
  const [title, setTitle] = useState("");
  const [number, setNumber] = useState("");
  const [issuingOrg, setIssuingOrg] = useState("");
  const [issuedAt, setIssuedAt] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [fileId, setFileId] = useState("");

  useEffect(() => {
    if (!open) return;
    setDocType(initialData?.doc_type ?? "license");
    setTitle(initialData?.title ?? "");
    setNumber(initialData?.number ?? "");
    setIssuingOrg(initialData?.issuing_org ?? "");
    setIssuedAt(initialData?.issued_at ?? "");
    setValidUntil(initialData?.valid_until ?? "");
    setEmployeeId(initialData?.employee_id ?? "");
    setFileId(initialData?.file_id ?? "");
  }, [open, initialData]);

  const onSubmit = async () => {
    if (!title.trim()) {
      toast.error("Укажите название документа");
      return;
    }
    setSubmitting(true);
    try {
      const common = {
        doc_type: docType,
        title: title.trim(),
        number: number || null,
        issuing_org: issuingOrg || null,
        issued_at: issuedAt || null,
        valid_until: validUntil || null,
        file_id: fileId || null
      };
      if (initialData) {
        await contractorsApi.updateDocument(initialData.id, common);
      } else {
        await contractorsApi.createDocument({ contractor_id: contractorId, employee_id: employeeId || null, ...common });
      }
      toast.success(isEdit ? "Документ обновлён" : "Документ добавлен");
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      const e = err as { status?: number; message?: string };
      if (e.status === 422) {
        toast.error("Сотрудник не принадлежит выбранному подрядчику");
      } else {
        toast.error(e.message ?? "Не удалось сохранить документ");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать документ" : "Новый документ"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="doc-type">Тип документа</Label>
              <select id="doc-type" className="h-10 w-full rounded-md border px-3" value={docType} onChange={(e) => setDocType(e.target.value as DocType)}>
                {DOC_TYPE_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {DOC_TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="doc-employee">Сотрудник (необязательно)</Label>
              <select
                id="doc-employee"
                className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
                value={employeeId}
                disabled={isEdit}
                onChange={(e) => setEmployeeId(e.target.value)}
              >
                <option value="">— На компанию —</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.full_name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="doc-title">Название</Label>
            <Input id="doc-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="doc-number">Номер</Label>
              <Input id="doc-number" value={number} onChange={(e) => setNumber(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="doc-org">Выдавший орган</Label>
              <Input id="doc-org" value={issuingOrg} onChange={(e) => setIssuingOrg(e.target.value)} />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="doc-issued">Выдан</Label>
              <Input id="doc-issued" type="date" value={issuedAt} onChange={(e) => setIssuedAt(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="doc-valid">Действует до</Label>
              <Input id="doc-valid" type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="doc-file">ID файла (необязательно)</Label>
            <Input id="doc-file" value={fileId} onChange={(e) => setFileId(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => void onSubmit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

- [ ] **Step 4: Create the documents tab**

Create `frontend/src/features/contractors/ContractorDocumentsTab.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";

import { contractorsApi, isFeatureDisabledError } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Can } from "@/components/permissions/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ContractorDocumentFormDialog } from "@/features/contractors/ContractorDocumentFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { DOC_TYPE_LABELS, DOC_TYPE_OPTIONS, EXPIRY_BADGE_VARIANT, EXPIRY_LABELS } from "@/pages/contractors/contractorsVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import { formatDate } from "@/utils/datetime";
import type { ContractorDocument, ContractorEmployee, DocType } from "@/types/dto/contractors";

export const ContractorDocumentsTab = ({ contractorId }: { contractorId: string }) => {
  const [docTypeFilter, setDocTypeFilter] = useState<DocType | "">("");
  const [employees, setEmployees] = useState<ContractorEmployee[]>([]);

  const loader = useCallback(
    () =>
      contractorsApi
        .listDocuments({ contractor_id: contractorId, ...(docTypeFilter ? { doc_type: docTypeFilter } : {}) })
        .then((p) => p.items),
    [contractorId, docTypeFilter]
  );
  const { data, loading, error, reload } = useAsyncResource<ContractorDocument[]>({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить документы"
  });

  useEffect(() => {
    contractorsApi
      .listEmployees({ contractor_id: contractorId })
      .then((p) => setEmployees(p.items))
      .catch(() => undefined);
  }, [contractorId]);

  const onArchive = async (id: string) => {
    if (!window.confirm("Архивировать документ?")) return;
    try {
      await contractorsApi.archiveDocument(id);
      toast.success("Документ архивирован");
      void reload();
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось архивировать документ");
    }
  };

  const registry = useLocalRegistry({
    items: data,
    match: (item, query) => [item.title, item.number, item.issuing_org].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  const columns: ColumnDef<ContractorDocument, unknown>[] = [
    { accessorKey: "title", header: "Документ" },
    { accessorKey: "doc_type", header: "Тип", cell: ({ row }) => DOC_TYPE_LABELS[row.original.doc_type] ?? row.original.doc_type },
    { accessorKey: "valid_until", header: "Действует до", cell: ({ row }) => formatDate(row.original.valid_until ?? "") || "—" },
    {
      accessorKey: "expiry_status",
      header: "Состояние",
      cell: ({ row }) => <Badge variant={EXPIRY_BADGE_VARIANT[row.original.expiry_status]}>{EXPIRY_LABELS[row.original.expiry_status]}</Badge>
    },
    {
      id: "actions",
      header: "Действия",
      cell: ({ row }) => (
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE} fallback={<span className="text-muted-foreground">—</span>}>
          <div className="flex gap-2">
            <ContractorDocumentFormDialog
              trigger={<Button variant="ghost" size="sm">Изменить</Button>}
              contractorId={contractorId}
              employees={employees}
              initialData={row.original}
              onSubmitted={() => void reload()}
            />
            <Button variant="ghost" size="sm" onClick={() => void onArchive(row.original.id)}>
              Архивировать
            </Button>
          </div>
        </Can>
      )
    }
  ];

  if (error && isFeatureDisabledError(error)) {
    return <EmptyState title="Функция недоступна" description="Документы подрядчиков не включены для этого тенанта." />;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <select
          className="h-9 rounded-md border px-3 text-sm"
          value={docTypeFilter}
          onChange={(e) => setDocTypeFilter(e.target.value as DocType | "")}
          aria-label="Фильтр по типу документа"
        >
          <option value="">Все типы</option>
          {DOC_TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {DOC_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
          <ContractorDocumentFormDialog
            trigger={<Button>Добавить документ</Button>}
            contractorId={contractorId}
            employees={employees}
            onSubmitted={() => void reload()}
          />
        </Can>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка документов" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState title="Документов нет" description="Добавьте документ подрядчика." />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={columns}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по документу"
          caption="Документы подрядчика"
        />
      ) : null}
    </div>
  );
};
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/features/contractors/ContractorDocumentsTab.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add -- frontend/src/features/contractors/ContractorDocumentFormDialog.tsx frontend/src/features/contractors/ContractorDocumentsTab.tsx frontend/src/features/contractors/ContractorDocumentsTab.test.tsx
git commit -m "feat(contractors): documents tab with type filter, create/edit/archive, soft feature state"
```

---

## Task 11: Инциденты tab + `ContractorIncidentFormDialog`

**Files:**
- Create: `frontend/src/features/contractors/ContractorIncidentFormDialog.tsx`
- Create: `frontend/src/features/contractors/ContractorIncidentsTab.tsx`
- Test: `frontend/src/features/contractors/ContractorIncidentsTab.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/contractors/ContractorIncidentsTab.test.tsx`:

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { ContractorIncidentsTab } from "./ContractorIncidentsTab";
import { contractorsApi } from "@/api/contractors";

vi.mock("@/api/contractors", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contractors")>();
  return {
    ...actual,
    contractorsApi: {
      listIncidents: vi.fn(),
      createIncident: vi.fn()
    }
  };
});

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: unknown }) =>
    typeof children === "function" ? (children as (v: boolean) => unknown)(true) : children
}));

beforeEach(() => {
  vi.clearAllMocks();
  (contractorsApi.listIncidents as any).mockResolvedValue({
    items: [{ id: "i1", contractor_id: "c1", incident_type: "падение", severity: "high", status: "open", occurred_at: "2026-06-01T10:00:00Z" }],
    total: 1
  });
  (contractorsApi.createIncident as any).mockResolvedValue({ id: "i2" });
});

describe("ContractorIncidentsTab", () => {
  it("lists incidents scoped by contractor", async () => {
    render(<ContractorIncidentsTab contractorId="c1" />);
    expect(await screen.findByText("падение")).toBeInTheDocument();
    expect(contractorsApi.listIncidents).toHaveBeenCalledWith({ contractor_id: "c1" });
  });

  it("registers an incident", async () => {
    render(<ContractorIncidentsTab contractorId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Зарегистрировать инцидент" }));
    fireEvent.change(await screen.findByLabelText("Тип инцидента"), { target: { value: "порез" } });
    fireEvent.change(screen.getByLabelText("Дата и время"), { target: { value: "2026-06-02T09:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(contractorsApi.createIncident).toHaveBeenCalledWith(
        expect.objectContaining({ contractor_id: "c1", incident_type: "порез", severity: "medium" })
      )
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- src/features/contractors/ContractorIncidentsTab.test.tsx`
Expected: FAIL — modules do not exist.

- [ ] **Step 3: Create the incident dialog**

Create `frontend/src/features/contractors/ContractorIncidentFormDialog.tsx`:

```tsx
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { contractorsApi } from "@/api/contractors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SEVERITY_LABELS, SEVERITY_OPTIONS } from "@/pages/contractors/contractorsVocab";
import type { IncidentSeverity } from "@/types/dto/contractors";

interface Props {
  trigger: ReactNode;
  contractorId: string;
  onSubmitted?: () => void;
}

export const ContractorIncidentFormDialog = ({ trigger, contractorId, onSubmitted }: Props) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [incidentType, setIncidentType] = useState("");
  const [severity, setSeverity] = useState<IncidentSeverity>("medium");
  const [occurredAt, setOccurredAt] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (!open) return;
    setIncidentType("");
    setSeverity("medium");
    setOccurredAt("");
    setDescription("");
  }, [open]);

  const onSubmit = async () => {
    if (!incidentType.trim()) {
      toast.error("Укажите тип инцидента");
      return;
    }
    if (!occurredAt) {
      toast.error("Укажите дату и время");
      return;
    }
    setSubmitting(true);
    try {
      await contractorsApi.createIncident({
        contractor_id: contractorId,
        incident_type: incidentType.trim(),
        severity,
        occurred_at: new Date(occurredAt).toISOString(),
        description: description || null
      });
      toast.success("Инцидент зарегистрирован");
      onSubmitted?.();
      setOpen(false);
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Не удалось сохранить инцидент");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новый инцидент подрядчика</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="inc-type">Тип инцидента</Label>
            <Input id="inc-type" value={incidentType} onChange={(e) => setIncidentType(e.target.value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="inc-severity">Тяжесть</Label>
              <select id="inc-severity" className="h-10 w-full rounded-md border px-3" value={severity} onChange={(e) => setSeverity(e.target.value as IncidentSeverity)}>
                {SEVERITY_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {SEVERITY_LABELS[s]}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="inc-date">Дата и время</Label>
              <Input id="inc-date" type="datetime-local" value={occurredAt} onChange={(e) => setOccurredAt(e.target.value)} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="inc-desc">Описание</Label>
            <Textarea id="inc-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => void onSubmit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

- [ ] **Step 4: Create the incidents tab**

Create `frontend/src/features/contractors/ContractorIncidentsTab.tsx`:

```tsx
import { useCallback } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { contractorsApi } from "@/api/contractors";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Can } from "@/components/permissions/Can";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ContractorIncidentFormDialog } from "@/features/contractors/ContractorIncidentFormDialog";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { SEVERITY_LABELS } from "@/pages/contractors/contractorsVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import { formatDate } from "@/utils/datetime";
import type { ContractorIncident, IncidentSeverity } from "@/types/dto/contractors";

const severityVariant = (s: IncidentSeverity): "default" | "secondary" | "destructive" =>
  s === "critical" || s === "high" ? "destructive" : s === "medium" ? "secondary" : "default";

export const ContractorIncidentsTab = ({ contractorId }: { contractorId: string }) => {
  const loader = useCallback(() => contractorsApi.listIncidents({ contractor_id: contractorId }).then((p) => p.items), [contractorId]);
  const { data, loading, error, reload } = useAsyncResource<ContractorIncident[]>({
    loader,
    initialData: [],
    errorMessage: "Не удалось загрузить инциденты"
  });

  const registry = useLocalRegistry({
    items: data,
    match: (item, query) => [item.incident_type, item.status].filter(Boolean).join(" ").toLowerCase().includes(query)
  });

  const columns: ColumnDef<ContractorIncident, unknown>[] = [
    { accessorKey: "incident_type", header: "Тип" },
    {
      accessorKey: "severity",
      header: "Тяжесть",
      cell: ({ row }) => <Badge variant={severityVariant(row.original.severity)}>{SEVERITY_LABELS[row.original.severity]}</Badge>
    },
    { accessorKey: "status", header: "Статус", cell: ({ row }) => row.original.status || "—" },
    { accessorKey: "occurred_at", header: "Когда", cell: ({ row }) => formatDate(row.original.occurred_at) || "—" }
  ];

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Can permission={PERMISSIONS.CONTRACTOR_MANAGE}>
          <ContractorIncidentFormDialog
            trigger={<Button>Зарегистрировать инцидент</Button>}
            contractorId={contractorId}
            onSubmitted={() => void reload()}
          />
        </Can>
      </div>
      <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
      {loading ? <LoadingScreen label="Загрузка инцидентов" /> : null}
      {!loading && !error && registry.total === 0 ? (
        <EmptyState title="Инцидентов нет" description="Инциденты по этому подрядчику не зарегистрированы." />
      ) : null}
      {!loading && !error && registry.total > 0 ? (
        <RegistryTable
          columns={columns}
          data={registry.pagedItems}
          pageIndex={registry.pageIndex}
          pageSize={registry.pageSize}
          total={registry.total}
          onPageChange={registry.onPageChange}
          onPageSizeChange={registry.onPageSizeChange}
          onSearchChange={registry.onSearchChange}
          searchPlaceholder="Поиск по типу инцидента"
          caption="Инциденты подрядчика"
        />
      ) : null}
    </div>
  );
};
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm --prefix frontend run test -- src/features/contractors/ContractorIncidentsTab.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add -- frontend/src/features/contractors/ContractorIncidentFormDialog.tsx frontend/src/features/contractors/ContractorIncidentsTab.tsx frontend/src/features/contractors/ContractorIncidentsTab.test.tsx
git commit -m "feat(contractors): incidents tab with register dialog"
```

---

## Task 12: Full gates + browser verification

**Files:** none (verification only)

- [ ] **Step 1: Typecheck the whole frontend**

Run: `npm --prefix frontend run typecheck`
Expected: PASS with zero errors (the Task 3 placeholder error is now resolved by Task 7).

- [ ] **Step 2: Run the full contractors test set**

Run: `npm --prefix frontend run test -- src/api/contractors.test.ts src/pages/contractors src/features/contractors`
Expected: PASS — all suites green (api client, ContractorsPage, ContractorDetailPage, employees/admission/documents/incidents tabs).

- [ ] **Step 3: Production build**

Run: `npm --prefix frontend run build`
Expected: build succeeds (lazy `ContractorDetailPage` chunk emitted).

- [ ] **Step 4: Browser verification**

Enable the `contractors` feature flag for the demo tenant (so documents/admission/requirements are exercised, not soft-stated). Then:

1. `preview_start` the dev server (`.claude/launch.json`; create a config running `python scripts/dev_lite.py` if none exists). Log in with `demo` / `admin@example.com` / `admin123`.
2. Navigate to `/contractors`. Verify: registry table renders, three tabs present, "Новый контрагент" creates a contractor (reappears in table).
3. Open a contractor → `/contractors/:id`. Verify the four tabs.
4. Сотрудники: add an employee; open "Допуск" → readiness + checklist render; click "Допустить" and observe verdict/violations.
5. Документы: add a document; filter by type; archive one.
6. Инциденты: register an incident.
7. Требования к документам (list page tab): add and delete a requirement.
8. Check `read_console_messages` for errors and `read_network_requests` for the `/api/v1/contractors/*` calls returning 2xx.
9. Screenshot the detail page (`computer` action `screenshot`) as proof.

- [ ] **Step 5: Final commit (if any verification fixes were needed)**

```bash
git add -- frontend/src
git commit -m "fix(contractors): browser-verification adjustments"
```

(If no fixes were needed, skip this commit.)

---

## Self-Review

**Spec coverage — all 23 endpoints mapped to a task:**
- Registry list/create/get/patch/delete → Tasks 2, 4, 5, 7 ✅
- Employees list/create/patch → Tasks 2, 8 ✅
- Admission readiness/checklist/admit → Tasks 2, 9 ✅
- Incidents list/create → Tasks 2, 11 ✅
- Compliance-summary → Tasks 2, 7 ✅
- Documents list/create/expiring/get/patch/delete → Tasks 2, 6, 10 ✅
- Document-requirements list/create/delete → Tasks 2, 6 ✅
- Permissions + routing → Task 3 ✅
- Feature-flag soft state → Tasks 2 (`isFeatureDisabledError`), 6, 10 ✅

**Type consistency:** API method names (`listRegistry`, `getRegistry`, `createRegistry`, `updateRegistry`, `archiveRegistry`, `listEmployees`, `createEmployee`, `updateEmployee`, `getEmployeeReadiness`, `getEmployeeChecklist`, `admitEmployee`, `listIncidents`, `createIncident`, `getComplianceSummary`, `listDocuments`, `listExpiringDocuments`, `getDocument`, `createDocument`, `updateDocument`, `archiveDocument`, `listRequirements`, `createRequirement`, `deleteRequirement`) are used consistently across Tasks 2/5/6/7/8/9/10/11. DTO field names match `backend/app/api/routes/contractors.py` response bodies.

**Cross-task ordering note:** `ContractorsPage` (Task 5) imports Task 6 components; `ContractorDetailPage` (Task 7) imports Tasks 8–11 components. Under subagent-driven execution, treat 5+6 and 7+8+9+10+11 as ordered groups — the "run test" steps that depend on later files are explicitly marked "(after Task N)". Typecheck is fully green only after Task 11; the final gate is Task 12.
```
