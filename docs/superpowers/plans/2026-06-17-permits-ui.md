# Permits UI (Л1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the admin-only "Личные допуски" screen (`/permits`) on top of the already-merged backend `/permits` API: list with filters, create/edit, extend, revoke.

**Architecture:** Frontend-only. Follows existing page conventions — data via `useAsyncResource` + a thin api module (`api/permits.ts`), local search/pagination via `useLocalRegistry`, modal forms via `react-hook-form` + `zod` (like `PersonFormDialog`). No Zustand store (used only on this page — YAGNI). Gated by two new frontend permission codes granted only to `admin` via `ALL_PERMISSIONS`.

**Tech Stack:** React + TypeScript + Vite, react-hook-form, zod, TanStack Table (via shared `RegistryTable`), shadcn UI (`Dialog`, `Input`, `Badge`, `Button`), vitest + @testing-library/react, sonner toasts, axios (`apiClient`).

**Spec:** `docs/superpowers/specs/2026-06-17-permits-ui-design.md`

**Branch:** `feat/permits-ui` (already created; spec committed as `d5fdd7b`).

**Working directory for all frontend commands:** `frontend/` (run `cd frontend` first).

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/src/permissions/permissions.ts` (modify) | Add `PERMIT_VIEW`, `PERMIT_MANAGE` codes. |
| `frontend/src/types/dto/permits.ts` (create) | `PermitDto`, `PermitPage`, create/update payload types. |
| `frontend/src/types/forms/permits.ts` (create) | `permitFormSchema` (zod) + `PermitFormValues`. |
| `frontend/src/api/permits.ts` (create) | `permitsApi`: list/count/create/update/extend/revoke over `apiClient`. |
| `frontend/src/api/personsApi.ts` (modify) | Add `fetchAllPersons()` (tenant-wide person list for name mapping + dropdown). |
| `frontend/src/features/permits/PermitFormDialog.tsx` (create) | Create/edit permit modal. |
| `frontend/src/features/permits/PermitExtendDialog.tsx` (create) | Extend permit modal (single date). |
| `frontend/src/features/permits/RevokePermitDialog.tsx` (create) | Revoke confirmation modal. |
| `frontend/src/pages/permits/PermitsPage.tsx` (create) | Page: header+counters, filters, table, action wiring. |
| `frontend/src/__tests__/PermitsPage.test.tsx` (create) | Component test: render, empty, permission gate, status badge. |
| `frontend/src/router/pageRegistry.tsx` (modify) | Lazy-register `PermitsPage`. |
| `frontend/src/router/routeGroups.tsx` (modify) | Protected `/permits` route under `PERMIT_VIEW`. |
| `frontend/src/router/navigationConfig.ts` (modify) | Nav item "Личные допуски". |

---

### Task 1: Add frontend permission codes

**Files:**
- Modify: `frontend/src/permissions/permissions.ts` (after the `MEDICAL_VIEW` line, ~L30)

Admin already has `ALL_PERMISSIONS = Object.values(PERMISSIONS)`, so new codes are granted to `admin` automatically. **Do NOT add these to any other role** — the backend `/permits` is admin-only, so showing the page to a non-admin would render a screen whose API calls return 403.

- [ ] **Step 1: Add the two codes**

In `frontend/src/permissions/permissions.ts`, inside the `PERMISSIONS` object, immediately after the `MEDICAL_VIEW: "medical.view",` line, add:

```typescript
  PERMIT_VIEW: "permit.view",
  PERMIT_MANAGE: "permit.manage",
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (no new errors). `PERMIT_VIEW`/`PERMIT_MANAGE` now exist on `PERMISSIONS` and flow into the `Permission` union + `ALL_PERMISSIONS`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/permissions/permissions.ts
git commit -m "feat(permits): add permit.view/permit.manage frontend permission codes (admin-only)"
```

---

### Task 2: DTO and form types

**Files:**
- Create: `frontend/src/types/dto/permits.ts`
- Create: `frontend/src/types/forms/permits.ts`
- Test: `frontend/src/__tests__/permitForm.test.ts`

- [ ] **Step 1: Write the failing zod-schema test**

Create `frontend/src/__tests__/permitForm.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { permitFormSchema } from "@/types/forms/permits";

describe("permitFormSchema", () => {
  it("rejects missing person and type", () => {
    const result = permitFormSchema.safeParse({ person_id: "", permit_type: "" });
    expect(result.success).toBe(false);
  });

  it("accepts a valid permit form", () => {
    const result = permitFormSchema.safeParse({
      person_id: "p1",
      permit_type: "Работа на высоте",
      issued_at: "2026-01-12",
      valid_until: "2027-01-12"
    });
    expect(result.success).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/permitForm.test.ts`
Expected: FAIL — cannot resolve `@/types/forms/permits`.

- [ ] **Step 3: Create the DTO types**

Create `frontend/src/types/dto/permits.ts`:

```typescript
export type PermitStatus = "active" | "expired" | "revoked";

export interface PermitDto {
  id: string;
  person_id: string;
  position_id?: string | null;
  permit_type: string;
  issued_at: string;
  valid_until?: string | null;
  status: PermitStatus;
  is_expired: boolean;
  created_at: string;
  updated_at: string;
}

export interface PermitPage {
  items: PermitDto[];
  total: number;
}

export interface PermitCreatePayload {
  person_id: string;
  permit_type: string;
  issued_at?: string;
  valid_until?: string;
}

export interface PermitUpdatePayload {
  permit_type?: string;
  valid_until?: string;
}
```

- [ ] **Step 4: Create the form schema**

Create `frontend/src/types/forms/permits.ts`:

```typescript
import { z } from "zod";

export const permitFormSchema = z.object({
  person_id: z.string().trim().min(1, "Выберите сотрудника"),
  permit_type: z.string().trim().min(1, "Укажите тип допуска"),
  issued_at: z
    .string()
    .optional()
    .transform((s) => (s === undefined ? s : s.trim())),
  valid_until: z
    .string()
    .optional()
    .transform((s) => (s === undefined ? s : s.trim()))
});

export type PermitFormValues = z.infer<typeof permitFormSchema>;
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/permitForm.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/dto/permits.ts frontend/src/types/forms/permits.ts frontend/src/__tests__/permitForm.test.ts
git commit -m "feat(permits): DTO + zod form schema for permits UI"
```

---

### Task 3: API module + tenant-wide persons fetch

**Files:**
- Create: `frontend/src/api/permits.ts`
- Modify: `frontend/src/api/personsApi.ts` (append `fetchAllPersons`)

- [ ] **Step 1: Create the permits api module**

Create `frontend/src/api/permits.ts`:

```typescript
import { apiClient } from "@/api/client";
import type {
  PermitCreatePayload,
  PermitDto,
  PermitPage,
  PermitUpdatePayload
} from "@/types/dto/permits";

const BASE = "/permits";

export type PermitListParams = {
  person_id?: string;
  status?: string;
  expired_only?: boolean;
  limit?: number;
  offset?: number;
};

export const permitsApi = {
  async listPermits(params: PermitListParams = {}): Promise<PermitPage> {
    const { data } = await apiClient.get<PermitPage>(BASE, {
      params: { limit: 200, offset: 0, ...params }
    });
    return { items: data.items ?? [], total: data.total ?? 0 };
  },

  async countPermits(params: Omit<PermitListParams, "limit" | "offset"> = {}): Promise<number> {
    const { data } = await apiClient.get<PermitPage>(BASE, {
      params: { ...params, limit: 1, offset: 0 }
    });
    return data.total ?? 0;
  },

  async createPermit(payload: PermitCreatePayload): Promise<PermitDto> {
    const { data } = await apiClient.post<PermitDto>(BASE, payload);
    return data;
  },

  async updatePermit(id: string, payload: PermitUpdatePayload): Promise<PermitDto> {
    const { data } = await apiClient.patch<PermitDto>(`${BASE}/${id}`, payload);
    return data;
  },

  async extendPermit(id: string, validUntil: string): Promise<PermitDto> {
    const { data } = await apiClient.post<PermitDto>(`${BASE}/${id}/extend`, {
      valid_until: validUntil
    });
    return data;
  },

  async revokePermit(id: string): Promise<PermitDto> {
    const { data } = await apiClient.post<PermitDto>(`${BASE}/${id}/revoke`, {});
    return data;
  }
};
```

- [ ] **Step 2: Append `fetchAllPersons` to personsApi.ts**

In `frontend/src/api/personsApi.ts`, after the existing `fetchPersonsForCompany` function (end of file), add:

```typescript
/** Все сотрудники тенанта (для маппинга person_id→ФИО и выпадающего списка в форме допуска). */
export async function fetchAllPersons(listLimit = 500): Promise<PersonDto[]> {
  const { data } = await apiClient.get<PersonListResponse>("/persons", {
    params: { limit: listLimit, offset: 0 }
  });
  return (data.items ?? []).map((row) => normalizePersonRead(row));
}
```

(`PersonListResponse`, `normalizePersonRead`, `apiClient`, and `PersonDto` are already defined/imported in that file.)

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/permits.ts frontend/src/api/personsApi.ts
git commit -m "feat(permits): permitsApi (list/count/create/update/extend/revoke) + fetchAllPersons"
```

---

### Task 4: Create/edit form dialog

**Files:**
- Create: `frontend/src/features/permits/PermitFormDialog.tsx`

Mirrors `frontend/src/features/persons/PersonFormDialog.tsx`. On create: person is chosen from a dropdown. On edit: person is fixed (read-only) and `issued_at` is not editable (the backend `PermitUpdate` accepts only `permit_type` + `valid_until`).

- [ ] **Step 1: Create the dialog component**

Create `frontend/src/features/permits/PermitFormDialog.tsx`:

```tsx
import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { permitsApi } from "@/api/permits";
import type { PermitDto } from "@/types/dto/permits";
import type { PersonDto } from "@/types/dto/persons";
import { permitFormSchema, type PermitFormValues } from "@/types/forms/permits";
import { applyApiFieldErrorsToForm, isApiError } from "@/utils/apiFormErrors";

const emptyForm: PermitFormValues = {
  person_id: "",
  permit_type: "",
  issued_at: "",
  valid_until: ""
};

const PERMIT_API_FIELD_MAP: Record<string, keyof PermitFormValues> = {
  person_id: "person_id",
  permit_type: "permit_type",
  issued_at: "issued_at",
  valid_until: "valid_until"
};

interface PermitFormDialogProps {
  trigger: ReactNode;
  persons: PersonDto[];
  initialData?: PermitDto;
  onSubmitted?: (permit: PermitDto) => void;
}

export const PermitFormDialog = ({ trigger, persons, initialData, onSubmitted }: PermitFormDialogProps) => {
  const [open, setOpen] = useState(false);
  const isEdit = Boolean(initialData);

  const form = useForm<PermitFormValues>({
    resolver: zodResolver(permitFormSchema),
    defaultValues: emptyForm
  });

  useEffect(() => {
    if (!open) return;
    if (initialData) {
      form.reset({
        person_id: initialData.person_id,
        permit_type: initialData.permit_type,
        issued_at: initialData.issued_at ?? "",
        valid_until: initialData.valid_until ?? ""
      });
    } else {
      form.reset(emptyForm);
    }
  }, [open, initialData, form]);

  const onSubmit = async (values: PermitFormValues) => {
    try {
      const result = initialData
        ? await permitsApi.updatePermit(initialData.id, {
            permit_type: values.permit_type,
            valid_until: values.valid_until || undefined
          })
        : await permitsApi.createPermit({
            person_id: values.person_id,
            permit_type: values.permit_type,
            issued_at: values.issued_at || undefined,
            valid_until: values.valid_until || undefined
          });
      onSubmitted?.(result);
      toast.success(initialData ? "Допуск обновлён" : "Допуск создан");
      setOpen(false);
    } catch (err: unknown) {
      if (isApiError(err)) {
        applyApiFieldErrorsToForm(form.setError, err, PERMIT_API_FIELD_MAP);
        toast.error(err.message ?? "Не удалось сохранить допуск");
      } else {
        toast.error("Не удалось сохранить допуск");
      }
      throw err;
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? "Редактировать допуск" : "Новый допуск"}</DialogTitle>
          <DialogDescription>Заполните данные личного допуска сотрудника.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit(async (values) => {
            try {
              await onSubmit(values);
            } catch {
              /* toast уже показан в onSubmit */
            }
          })}
        >
          <div className="space-y-2">
            <Label htmlFor="person_id">Сотрудник</Label>
            <select
              id="person_id"
              className="h-10 w-full rounded-md border px-3 disabled:opacity-60"
              disabled={isEdit}
              {...form.register("person_id")}
            >
              <option value="">— Выберите сотрудника —</option>
              {persons.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.full_name}
                </option>
              ))}
            </select>
            {form.formState.errors.person_id && (
              <p className="text-xs text-destructive">{form.formState.errors.person_id.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="permit_type">Тип допуска</Label>
            <Input id="permit_type" placeholder="напр. Работа на высоте" {...form.register("permit_type")} />
            {form.formState.errors.permit_type && (
              <p className="text-xs text-destructive">{form.formState.errors.permit_type.message}</p>
            )}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="issued_at">Выдан</Label>
              <Input id="issued_at" type="date" disabled={isEdit} {...form.register("issued_at")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="valid_until">Действует до</Label>
              <Input id="valid_until" type="date" {...form.register("valid_until")} />
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/permits/PermitFormDialog.tsx
git commit -m "feat(permits): create/edit permit form dialog"
```

---

### Task 5: Extend + revoke dialogs

**Files:**
- Create: `frontend/src/features/permits/PermitExtendDialog.tsx`
- Create: `frontend/src/features/permits/RevokePermitDialog.tsx`

- [ ] **Step 1: Create the extend dialog**

Create `frontend/src/features/permits/PermitExtendDialog.tsx`:

```tsx
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { permitsApi } from "@/api/permits";
import type { PermitDto } from "@/types/dto/permits";

interface PermitExtendDialogProps {
  trigger: ReactNode;
  permit: PermitDto;
  onSubmitted?: (permit: PermitDto) => void;
}

export const PermitExtendDialog = ({ trigger, permit, onSubmitted }: PermitExtendDialogProps) => {
  const [open, setOpen] = useState(false);
  const [validUntil, setValidUntil] = useState(permit.valid_until ?? "");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) setValidUntil(permit.valid_until ?? "");
  }, [open, permit.valid_until]);

  const submit = async () => {
    if (!validUntil) {
      toast.error("Укажите новую дату");
      return;
    }
    setSubmitting(true);
    try {
      const result = await permitsApi.extendPermit(permit.id, validUntil);
      onSubmitted?.(result);
      toast.success("Допуск продлён");
      setOpen(false);
    } catch (err: unknown) {
      const message = err && typeof err === "object" && "message" in err ? String(err.message) : "Не удалось продлить допуск";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Продлить допуск</DialogTitle>
          <DialogDescription>Задайте новую дату «действует до».</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="extend_valid_until">Действует до</Label>
          <Input
            id="extend_valid_until"
            type="date"
            value={validUntil}
            onChange={(e) => setValidUntil(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button onClick={() => void submit()} disabled={submitting}>
            {submitting ? "Сохранение..." : "Продлить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

- [ ] **Step 2: Create the revoke confirmation dialog**

Create `frontend/src/features/permits/RevokePermitDialog.tsx`:

```tsx
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { permitsApi } from "@/api/permits";
import type { PermitDto } from "@/types/dto/permits";

interface RevokePermitDialogProps {
  trigger: ReactNode;
  permit: PermitDto;
  onSubmitted?: (permit: PermitDto) => void;
}

export const RevokePermitDialog = ({ trigger, permit, onSubmitted }: RevokePermitDialogProps) => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      const result = await permitsApi.revokePermit(permit.id);
      onSubmitted?.(result);
      toast.success("Допуск отозван");
      setOpen(false);
    } catch (err: unknown) {
      const message = err && typeof err === "object" && "message" in err ? String(err.message) : "Не удалось отозвать допуск";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Отозвать допуск?</DialogTitle>
          <DialogDescription>
            Допуск «{permit.permit_type}» будет отозван без возможности восстановления.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="destructive" onClick={() => void submit()} disabled={submitting}>
            {submitting ? "Отзыв..." : "Отозвать"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/permits/PermitExtendDialog.tsx frontend/src/features/permits/RevokePermitDialog.tsx
git commit -m "feat(permits): extend + revoke action dialogs"
```

---

### Task 6: Permits page + component test

**Files:**
- Create: `frontend/src/pages/permits/PermitsPage.tsx`
- Test: `frontend/src/__tests__/PermitsPage.test.tsx`

- [ ] **Step 1: Write the failing component test**

Create `frontend/src/__tests__/PermitsPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERMISSIONS } from "@/permissions/permissions";
import PermitsPage from "@/pages/permits/PermitsPage";
import { useAuthStore } from "@/stores/auth";

const listPermitsMock = vi.fn();
const countPermitsMock = vi.fn();
const fetchAllPersonsMock = vi.fn();

vi.mock("@/api/permits", () => ({
  permitsApi: {
    listPermits: (...args: unknown[]) => listPermitsMock(...args),
    countPermits: (...args: unknown[]) => countPermitsMock(...args),
    createPermit: vi.fn(),
    updatePermit: vi.fn(),
    extendPermit: vi.fn(),
    revokePermit: vi.fn()
  }
}));

vi.mock("@/api/personsApi", () => ({
  fetchAllPersons: (...args: unknown[]) => fetchAllPersonsMock(...args)
}));

const setUser = (permissions: string[]) =>
  useAuthStore.setState({
    user: { id: "u1", email: "a@a.io", roles: ["admin"], permissions },
    loading: false,
    error: null,
    isAuthenticated: true,
    initialized: true
  } as never);

describe("PermitsPage", () => {
  beforeEach(() => {
    listPermitsMock.mockReset();
    countPermitsMock.mockReset();
    fetchAllPersonsMock.mockReset();
    countPermitsMock.mockResolvedValue(0);
    fetchAllPersonsMock.mockResolvedValue([{ id: "p1", full_name: "Иванов И. И." }]);
  });

  it("shows empty state when there are no permits", async () => {
    listPermitsMock.mockResolvedValue({ items: [], total: 0 });
    setUser([PERMISSIONS.PERMIT_VIEW, PERMISSIONS.PERMIT_MANAGE]);
    render(
      <MemoryRouter>
        <PermitsPage />
      </MemoryRouter>
    );
    expect(await screen.findByText(/Допуски не найдены/i)).toBeInTheDocument();
  });

  it("renders a permit row with employee name and an expired badge", async () => {
    listPermitsMock.mockResolvedValue({
      items: [
        {
          id: "perm1",
          person_id: "p1",
          permit_type: "Работа на высоте",
          issued_at: "2025-01-01",
          valid_until: "2025-12-01",
          status: "active",
          is_expired: true,
          created_at: "2025-01-01T00:00:00Z",
          updated_at: "2025-01-01T00:00:00Z"
        }
      ],
      total: 1
    });
    setUser([PERMISSIONS.PERMIT_VIEW, PERMISSIONS.PERMIT_MANAGE]);
    render(
      <MemoryRouter>
        <PermitsPage />
      </MemoryRouter>
    );
    expect(await screen.findByText("Иванов И. И.")).toBeInTheDocument();
    expect(screen.getByText("Просрочен")).toBeInTheDocument();
  });

  it("disables the create button without permit.manage permission", async () => {
    listPermitsMock.mockResolvedValue({ items: [], total: 0 });
    setUser([PERMISSIONS.PERMIT_VIEW]);
    render(
      <MemoryRouter>
        <PermitsPage />
      </MemoryRouter>
    );
    expect(await screen.findByRole("button", { name: /Новый допуск/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/PermitsPage.test.tsx`
Expected: FAIL — cannot resolve `@/pages/permits/PermitsPage`.

- [ ] **Step 3: Create the page**

Create `frontend/src/pages/permits/PermitsPage.tsx`:

```tsx
import { useCallback, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { permitsApi } from "@/api/permits";
import { fetchAllPersons } from "@/api/personsApi";
import { Can } from "@/components/permissions/Can";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { PERMISSIONS } from "@/permissions/permissions";
import type { PermitDto } from "@/types/dto/permits";
import type { PersonDto } from "@/types/dto/persons";
import { formatDate } from "@/utils/datetime";
import { PermitFormDialog } from "@/features/permits/PermitFormDialog";
import { PermitExtendDialog } from "@/features/permits/PermitExtendDialog";
import { RevokePermitDialog } from "@/features/permits/RevokePermitDialog";

type PermitsData = {
  permits: PermitDto[];
  persons: PersonDto[];
  counts: { total: number; active: number; expired: number };
};

const permitBadge = (p: PermitDto): { label: string; variant: "default" | "secondary" | "destructive" } => {
  if (p.status === "revoked") return { label: "Отозван", variant: "secondary" };
  if (p.is_expired || p.status === "expired") return { label: "Просрочен", variant: "destructive" };
  return { label: "Действует", variant: "default" };
};

const PermitsPage = () => {
  const [statusFilter, setStatusFilter] = useState("");
  const [expiredOnly, setExpiredOnly] = useState(false);

  const loader = useCallback(async (): Promise<PermitsData> => {
    const params: Record<string, string | boolean | number> = {};
    if (expiredOnly) params.expired_only = true;
    else if (statusFilter) params.status = statusFilter;
    const [page, persons, total, active, expired] = await Promise.all([
      permitsApi.listPermits(params),
      fetchAllPersons(),
      permitsApi.countPermits({}),
      permitsApi.countPermits({ status: "active" }),
      permitsApi.countPermits({ expired_only: true })
    ]);
    return { permits: page.items, persons, counts: { total, active, expired } };
  }, [statusFilter, expiredOnly]);

  const { data, loading, error, reload } = useAsyncResource<PermitsData>({
    loader,
    initialData: { permits: [], persons: [], counts: { total: 0, active: 0, expired: 0 } },
    errorMessage: "Не удалось загрузить допуски"
  });

  const personName = useMemo(() => {
    const map = new Map(data.persons.map((p) => [p.id, p.full_name]));
    return (id: string) => map.get(id) ?? id;
  }, [data.persons]);

  const registry = useLocalRegistry({
    items: data.permits,
    match: (permit, query) =>
      [personName(permit.person_id), permit.permit_type, permit.status]
        .join(" ")
        .toLowerCase()
        .includes(query)
  });

  const onChanged = () => void reload();

  const columns: ColumnDef<PermitDto, unknown>[] = [
    {
      id: "person",
      header: "Сотрудник",
      cell: ({ row }) => <span className="font-medium">{personName(row.original.person_id)}</span>
    },
    { accessorKey: "permit_type", header: "Тип допуска" },
    {
      accessorKey: "issued_at",
      header: "Выдан",
      cell: ({ row }) => formatDate(row.original.issued_at) || "—"
    },
    {
      accessorKey: "valid_until",
      header: "Действует до",
      cell: ({ row }) => formatDate(row.original.valid_until) || "—"
    },
    {
      accessorKey: "status",
      header: "Статус",
      cell: ({ row }) => {
        const badge = permitBadge(row.original);
        return <Badge variant={badge.variant}>{badge.label}</Badge>;
      }
    },
    {
      id: "actions",
      header: "Действия",
      cell: ({ row }) => {
        const permit = row.original;
        if (permit.status === "revoked") return <span className="text-muted-foreground">—</span>;
        return (
          <Can permission={PERMISSIONS.PERMIT_MANAGE} fallback={<span className="text-muted-foreground">—</span>}>
            <div className="flex gap-2">
              {permit.status === "active" ? (
                <PermitFormDialog
                  persons={data.persons}
                  initialData={permit}
                  onSubmitted={onChanged}
                  trigger={
                    <Button variant="ghost" size="sm">
                      Изменить
                    </Button>
                  }
                />
              ) : null}
              <PermitExtendDialog
                permit={permit}
                onSubmitted={onChanged}
                trigger={
                  <Button variant="ghost" size="sm">
                    Продлить
                  </Button>
                }
              />
              <RevokePermitDialog
                permit={permit}
                onSubmitted={onChanged}
                trigger={
                  <Button variant="ghost" size="sm">
                    Отозвать
                  </Button>
                }
              />
            </div>
          </Can>
        );
      }
    }
  ];

  return (
    <div className="space-y-4">
      <RegistryPageHeader
        title="Личные допуски"
        description="Кто к чему допущен и до какого срока. Реестр поверх backend `/permits`."
        stats={[
          { label: "Всего", value: data.counts.total },
          { label: "Действует", value: data.counts.active },
          { label: "Просрочено", value: data.counts.expired }
        ]}
        actions={
          <Can
            permission={PERMISSIONS.PERMIT_MANAGE}
            fallback={
              <Button disabled>Новый допуск</Button>
            }
          >
            <PermitFormDialog
              persons={data.persons}
              onSubmitted={onChanged}
              trigger={<Button>Новый допуск</Button>}
            />
          </Can>
        }
      />
      <Card>
        <CardContent className="space-y-3 pt-4">
          <div className="flex flex-wrap items-center gap-3">
            <select
              className="h-9 rounded-md border px-3 text-sm disabled:opacity-60"
              value={statusFilter}
              disabled={expiredOnly}
              onChange={(e) => setStatusFilter(e.target.value)}
              aria-label="Фильтр по статусу"
            >
              <option value="">Все статусы</option>
              <option value="active">Действует</option>
              <option value="expired">Просрочен</option>
              <option value="revoked">Отозван</option>
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={expiredOnly}
                onChange={(e) => setExpiredOnly(e.target.checked)}
              />
              Только просроченные
            </label>
          </div>

          <ErrorState error={error ?? undefined} onRetry={() => void reload()} />
          {loading ? <LoadingScreen label="Загрузка допусков" /> : null}
          {!loading && !error && registry.total === 0 ? (
            <EmptyState
              title="Допуски не найдены"
              description={registry.query ? "Измените запрос поиска." : "В этом tenant пока нет допусков."}
            />
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
              searchPlaceholder="Поиск по ФИО или типу допуска"
              caption="Реестр личных допусков"
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default PermitsPage;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/PermitsPage.test.tsx`
Expected: PASS (3 tests). If `useAuthStore.setState` shape differs, align the `setUser` object with the real store shape used in `frontend/src/__tests__/PpePage.test.tsx` (open that file and copy its `useAuthStore.setState({...})` shape exactly).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/permits/PermitsPage.tsx frontend/src/__tests__/PermitsPage.test.tsx
git commit -m "feat(permits): permits registry page + component test"
```

---

### Task 7: Wire routing and navigation

**Files:**
- Modify: `frontend/src/router/pageRegistry.tsx`
- Modify: `frontend/src/router/routeGroups.tsx`
- Modify: `frontend/src/router/navigationConfig.ts`

- [ ] **Step 1: Register the lazy page**

In `frontend/src/router/pageRegistry.tsx`, after the `PrescriptionsPage` lazy export line, add:

```typescript
export const PermitsPage = lazy(() => import("@/pages/permits/PermitsPage"));
```

- [ ] **Step 2: Add the protected route**

In `frontend/src/router/routeGroups.tsx`:

(a) add `PermitsPage` to the import block from `./pageRegistry` (after `PrescriptionsPage,`).

(b) add a new route group (place it right after the `INSPECTION_VIEW` group):

```tsx
      {
        permission: PERMISSIONS.PERMIT_VIEW,
        routes: [<Route key="/permits" path="/permits" element={<PermitsPage />} />]
      },
```

- [ ] **Step 3: Add the nav item**

In `frontend/src/router/navigationConfig.ts`, inside the `"ОТ и ПромБез"` group's `items` array, after the `Медосмотры/допуски` item, add (and make sure `ShieldCheck` is imported from `lucide-react` at the top — add it to the existing `lucide-react` import if missing):

```typescript
    { label: "Личные допуски", to: "/permits", icon: ShieldCheck, permission: PERMISSIONS.PERMIT_VIEW },
```

- [ ] **Step 4: Typecheck + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/router/pageRegistry.tsx frontend/src/router/routeGroups.tsx frontend/src/router/navigationConfig.ts
git commit -m "feat(permits): register /permits route + nav entry (admin-only)"
```

---

### Task 8: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the new tests**

Run: `cd frontend && npx vitest run src/__tests__/permitForm.test.ts src/__tests__/PermitsPage.test.tsx`
Expected: PASS (5 tests total).

- [ ] **Step 2: Typecheck, lint, build**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run build`
Expected: all PASS (build compiles the new lazy route).

- [ ] **Step 3: Manual preview check (verification skill)**

Start the dev server, open `/permits` as an admin user, confirm: list renders with ФИО + status badges; "Новый допуск" opens the form and creates a permit; "Изменить"/"Продлить"/"Отозвать" work and refresh the list; status filter + "только просроченные" re-query; counters reflect totals. Capture a screenshot for the user.

- [ ] **Step 4: Final summary commit (if any docs/touch-ups)**

If everything passes, the feature branch `feat/permits-ui` is ready. Hand back to the user for the finishing-a-development-branch decision (merge / PR).

---

## Self-Review

**Spec coverage:**
- §2 list + search + status filter + expired-only + counters → Task 6 (page) + Task 3 (count endpoint). ✅
- §2 create/edit/extend/revoke → Tasks 4, 5; wired in Task 6. ✅
- §3 admin-only via `permit.view`/`permit.manage` (not granted to other roles) → Task 1 + guards in Tasks 6/7. ✅
- §4 API contract usage (incl. `revoke` without body, `extend` `{valid_until}`, mutual-exclusion of status/expired_only) → Task 3 api module + Task 6 filter UI (select disabled when expired-only). ✅
- §6 parallel load of permits + persons + 3 counts; person_id→ФИО mapping → Task 6 loader + `personName`. ✅
- §7 status badge logic + action availability (edit active-only; extend/revoke active+expired; none for revoked) → Task 6 `permitBadge` + actions cell. ✅
- §8 form fields, person read-only on edit, `position_id` omitted → Task 4. ✅
- §9 error handling (ErrorState/EmptyState/toast on 409/404) → Tasks 4–6. ✅
- §10 component test (render, empty, permission gate, status badge) → Task 6 test. ✅
- §11 acceptance (admin-only, list correctness, actions, build green) → Task 8. ✅

**Placeholder scan:** No TBD/TODO; every code step has full code. ✅

**Type consistency:** `PermitDto`/`PermitPage`/`PermitCreatePayload`/`PermitUpdatePayload` defined in Task 2 and used identically in Tasks 3–6. `permitsApi` method names (`listPermits`, `countPermits`, `createPermit`, `updatePermit`, `extendPermit`, `revokePermit`) consistent across Tasks 3–6 and the test mock. `fetchAllPersons` defined in Task 3, imported in Task 6. `PERMIT_VIEW`/`PERMIT_MANAGE` defined in Task 1, used in Tasks 6–7. ✅

**Known soft spot:** the `useAuthStore.setState` shape in the Task 6 test is a best-effort guess; Step 4 instructs aligning it with the real shape from `PpePage.test.tsx` if it fails. This is the one place to double-check during execution.
