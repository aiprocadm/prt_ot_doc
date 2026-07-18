# P10-03 Medical Oversight UI (контингент / направления / отстранения) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать видимыми и управляемыми со страницы `/medical` три готовых backend-контура медосмотров: контингент (2 представления + печать DOCX/PDF), направления (полный FSM) и отстранения (list + lift).

**Architecture:** Чисто фронтовый срез (0 изменений `backend/`). Новые DTO+методы в `frontend/src/api/operations.ts`; три независимых `useAsyncResource`-блока и три новые секции в single-file `frontend/src/pages/medical/MedicalPage.tsx` (house-паттерн секционной страницы, прецедент `WarehousePage`); расширение словарей `StatusBadge`.

**Tech Stack:** React 18 + TypeScript, vitest + @testing-library/react, axios (`apiClient`), Tailwind-классы house-стиля.

**Спека:** `docs/superpowers/specs/2026-07-09-p10-03-medical-oversight-ui-design.md` (прочитать перед началом).

**Ветка:** `feat/p10-03-medical-oversight-ui` (уже создана от main@`5c06b3dc`).

---

## Операционные грабли (ЧИТАТЬ ПЕРВЫМ, из handoff'ов предыдущих срезов)

- В git-worktree НЕТ `node_modules` — если `frontend/node_modules` отсутствует, контроллер поднимает его ОДИН раз: `npm ci --prefer-offline` из `frontend/`. Субагентам НЕ переустанавливать.
- Фронт-гейты гонять через Bash-инструмент из каталога `frontend/`: `npx vitest run <файл>`. Node/npm в Git-Bash работают (в отличие от pytest).
- Полный `vitest run` НЕ гонять параллельно с каким-либо pytest (CPU-контеншн → ложные transform-fail). В этом срезе pytest не нужен вообще.
- При красном ПОЛНОМ прогоне vitest — перепроверить подозрительные файлы в изоляции перед дебагом (известный флейк параллелизма).
- Backend не трогаем: НЕ нужны pytest / OpenAPI snapshot / PG16-гейт / миграции.

## File Structure

- **Modify:** `frontend/src/api/operations.ts` — +5 DTO-типов, +9 методов `operationsApi`, +import `downloadBlob`.
- **Create:** `frontend/src/__tests__/medicalOversightApi.test.ts` — юнит-тест новых API-методов (мок `apiClient` + `downloadBlob`).
- **Modify:** `frontend/src/components/common/StatusBadge.tsx` — +6 статусов в оба словаря.
- **Create:** `frontend/src/components/common/StatusBadge.test.tsx` — тест новых лейблов.
- **Modify:** `frontend/src/pages/medical/MedicalPage.tsx` — шапка-stats из `/medical/summary` + 3 новые секции (вставляются МЕЖДУ блоком `RegistryTable` осмотров и секцией психиатрии).
- **Modify:** `frontend/src/pages/medical/MedicalPage.test.tsx` — полный мок `operationsApi` + ~11 новых тестов.
- **Modify (docs, Task 8):** `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md:655`, `CHANGELOG.md`, `AI_IMPLEMENTATION_REPORT.md`.

---

### Task 1: API-слой — DTO и методы `operationsApi`

**Files:**
- Modify: `frontend/src/api/operations.ts`
- Test: `frontend/src/__tests__/medicalOversightApi.test.ts` (create)

- [ ] **Step 1: Write the failing test**

Создать `frontend/src/__tests__/medicalOversightApi.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { operationsApi } from "@/api/operations";
import { downloadBlob } from "@/utils/download";

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
vi.mock("@/utils/download", () => ({ downloadBlob: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("operationsApi medical oversight methods", () => {
  it("getMedicalOversightSnapshot loads summary, register and named list", async () => {
    (apiClient.get as any).mockImplementation((url: string) => {
      if (url === "/medical/summary") {
        return Promise.resolve({ data: { by_status: { ok: 1 }, total: 3, overdue_count: 2, suspended_count: 1 } });
      }
      if (url === "/medical/contingent/register") {
        return Promise.resolve({ data: { items: [{ position_id: "pos1", position_name: "Электромонтёр", factors: [], headcount: 2, exam_kinds: ["periodic"], periodicity_months: 12 }], total: 1 } });
      }
      if (url === "/medical/named-list") {
        return Promise.resolve({ data: { items: [{ person_id: "p1", full_name: "Иванов Иван", factors: [], required_kinds: ["periodic"], status: "overdue" }], total: 1 } });
      }
      return Promise.reject(new Error(`unexpected url ${url}`));
    });
    const snapshot = await operationsApi.getMedicalOversightSnapshot();
    expect(snapshot.summary.total).toBe(3);
    expect(snapshot.register).toHaveLength(1);
    expect(snapshot.namedList[0].full_name).toBe("Иванов Иван");
  });

  it("downloadContingentRegisterPrint requests a blob and saves it", async () => {
    const blob = new Blob(["x"]);
    (apiClient.get as any).mockResolvedValue({ data: blob });
    await operationsApi.downloadContingentRegisterPrint("pdf");
    expect(apiClient.get).toHaveBeenCalledWith("/medical/contingent/register/print", {
      params: { format: "pdf" },
      responseType: "blob",
    });
    expect(downloadBlob).toHaveBeenCalledWith(blob, "contingent-register.pdf");
  });

  it("downloadNamedListPrint requests a blob and saves it", async () => {
    const blob = new Blob(["x"]);
    (apiClient.get as any).mockResolvedValue({ data: blob });
    await operationsApi.downloadNamedListPrint("docx");
    expect(apiClient.get).toHaveBeenCalledWith("/medical/named-list/print", {
      params: { format: "docx" },
      responseType: "blob",
    });
    expect(downloadBlob).toHaveBeenCalledWith(blob, "named-list.docx");
  });

  it("listMedicalReferrals passes the status filter only when set", async () => {
    (apiClient.get as any).mockResolvedValue({ data: { items: [], total: 0 } });
    await operationsApi.listMedicalReferrals({ status: "issued" });
    expect(apiClient.get).toHaveBeenCalledWith("/medical/referrals", {
      params: { limit: 100, offset: 0, status: "issued" },
    });
    await operationsApi.listMedicalReferrals();
    expect(apiClient.get).toHaveBeenLastCalledWith("/medical/referrals", {
      params: { limit: 100, offset: 0 },
    });
  });

  it("createMedicalReferral posts the payload", async () => {
    (apiClient.post as any).mockResolvedValue({ data: { id: "r1" } });
    await operationsApi.createMedicalReferral({ person_id: "p1", exam_kind: "periodic", due_at: "2026-08-01" });
    expect(apiClient.post).toHaveBeenCalledWith("/medical/referrals", {
      person_id: "p1",
      exam_kind: "periodic",
      due_at: "2026-08-01",
    });
  });

  it("transitionMedicalReferral posts to the transition endpoint", async () => {
    (apiClient.post as any).mockResolvedValue({ data: { id: "r1", status: "completed" } });
    await operationsApi.transitionMedicalReferral("r1", { to: "completed", result_exam_id: "e1" });
    expect(apiClient.post).toHaveBeenCalledWith("/medical/referrals/r1/transition", {
      to: "completed",
      result_exam_id: "e1",
    });
  });

  it("generateMedicalReferrals returns the created count", async () => {
    (apiClient.post as any).mockResolvedValue({ data: { count: 4 } });
    const result = await operationsApi.generateMedicalReferrals();
    expect(apiClient.post).toHaveBeenCalledWith("/medical/contingent/generate-referrals");
    expect(result.count).toBe(4);
  });

  it("listMedicalSuspensions passes status=active only when set", async () => {
    (apiClient.get as any).mockResolvedValue({ data: { items: [], total: 0 } });
    await operationsApi.listMedicalSuspensions({ status: "active" });
    expect(apiClient.get).toHaveBeenCalledWith("/medical/suspensions", { params: { status: "active" } });
    await operationsApi.listMedicalSuspensions();
    expect(apiClient.get).toHaveBeenLastCalledWith("/medical/suspensions", { params: {} });
  });

  it("liftMedicalSuspension posts to the lift endpoint", async () => {
    (apiClient.post as any).mockResolvedValue({ data: { id: "s1", status: "lifted" } });
    await operationsApi.liftMedicalSuspension("s1");
    expect(apiClient.post).toHaveBeenCalledWith("/medical/suspensions/s1/lift");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Из `frontend/`: `npx vitest run src/__tests__/medicalOversightApi.test.ts`
Expected: FAIL — `operationsApi.getMedicalOversightSnapshot is not a function` (и остальные методы).

- [ ] **Step 3: Write minimal implementation**

В `frontend/src/api/operations.ts`:

3a. Добавить импорт после строки 1 (`import { apiClient } from "@/api/client";`):

```ts
import { downloadBlob } from "@/utils/download";
```

3b. Добавить DTO-типы сразу после существующего `export type MedicalExamDto = {...};` (строка ~113-122):

```ts
export type ContingentRegisterRowDto = {
  position_id: string;
  position_name: string;
  factors: { code: string; name: string }[];
  headcount: number;
  exam_kinds: string[];
  periodicity_months?: number | null;
};

export type NamedListRowDto = {
  person_id: string;
  full_name: string;
  position_name?: string | null;
  department?: string | null;
  factors: { code: string; name: string }[];
  required_kinds: string[];
  last_exam_date?: string | null;
  next_due_date?: string | null;
  status: string;
};

export type MedicalReferralDto = {
  id: string;
  person_id: string;
  exam_kind: string;
  due_at?: string | null;
  status: "issued" | "scheduled" | "completed" | "cancelled";
  medical_org_name?: string | null;
  result_exam_id?: string | null;
  is_overdue: boolean;
};

export type MedicalSuspensionDto = {
  id: string;
  person_id: string;
  reason: "unfit" | "contraindication";
  status: "active" | "lifted";
  source_exam_id?: string | null;
};

export type MedicalSummaryDto = {
  by_status: Record<string, number>;
  total: number;
  overdue_count: number;
  suspended_count: number;
};
```

3c. Добавить методы в объект `operationsApi` сразу после метода `seedPsychiatricDefaults` (после строки ~330, перед `getFireSafetySnapshot`):

```ts
  getMedicalOversightSnapshot: async () => {
    const [summaryResponse, registerResponse, namedListResponse] = await Promise.all([
      apiClient.get<MedicalSummaryDto>("/medical/summary"),
      apiClient.get<{ items: ContingentRegisterRowDto[]; total: number }>("/medical/contingent/register"),
      apiClient.get<{ items: NamedListRowDto[]; total: number }>("/medical/named-list")
    ]);
    return {
      summary: summaryResponse.data,
      register: registerResponse.data.items ?? [],
      namedList: namedListResponse.data.items ?? []
    };
  },

  downloadContingentRegisterPrint: async (fmt: "docx" | "pdf") => {
    const { data } = await apiClient.get<Blob>("/medical/contingent/register/print", {
      params: { format: fmt },
      responseType: "blob"
    });
    downloadBlob(data, `contingent-register.${fmt}`);
  },

  downloadNamedListPrint: async (fmt: "docx" | "pdf") => {
    const { data } = await apiClient.get<Blob>("/medical/named-list/print", {
      params: { format: fmt },
      responseType: "blob"
    });
    downloadBlob(data, `named-list.${fmt}`);
  },

  listMedicalReferrals: async (params?: { status?: string }) => {
    const response = await apiClient.get<{ items: MedicalReferralDto[]; total: number }>("/medical/referrals", {
      params: { limit: 100, offset: 0, ...(params?.status ? { status: params.status } : {}) }
    });
    return response.data.items ?? [];
  },

  createMedicalReferral: async (payload: { person_id: string; exam_kind: string; due_at?: string; medical_org_name?: string }) => {
    const response = await apiClient.post<MedicalReferralDto>("/medical/referrals", payload);
    return response.data;
  },

  transitionMedicalReferral: async (referralId: string, payload: { to: string; result_exam_id?: string }) => {
    const response = await apiClient.post<MedicalReferralDto>(`/medical/referrals/${referralId}/transition`, payload);
    return response.data;
  },

  generateMedicalReferrals: async () => {
    const response = await apiClient.post<{ count: number }>("/medical/contingent/generate-referrals");
    return response.data;
  },

  listMedicalSuspensions: async (params?: { status?: "active" }) => {
    const response = await apiClient.get<{ items: MedicalSuspensionDto[]; total: number }>("/medical/suspensions", {
      params: params?.status ? { status: params.status } : {}
    });
    return response.data.items ?? [];
  },

  liftMedicalSuspension: async (suspensionId: string) => {
    const response = await apiClient.post<MedicalSuspensionDto>(`/medical/suspensions/${suspensionId}/lift`);
    return response.data;
  },
```

- [ ] **Step 4: Run test to verify it passes**

Из `frontend/`: `npx vitest run src/__tests__/medicalOversightApi.test.ts`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/operations.ts frontend/src/__tests__/medicalOversightApi.test.ts
git commit -m "feat(p10-03): operationsApi methods for medical oversight (contingent/referrals/suspensions)"
```

---

### Task 2: StatusBadge — статусы контингента / направлений / отстранений

**Files:**
- Modify: `frontend/src/components/common/StatusBadge.tsx`
- Test: `frontend/src/components/common/StatusBadge.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Создать `frontend/src/components/common/StatusBadge.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge medical oversight statuses", () => {
  it("renders russian labels for contingent/referral/suspension statuses", () => {
    render(
      <>
        <StatusBadge status="overdue" />
        <StatusBadge status="due_soon" />
        <StatusBadge status="missing" />
        <StatusBadge status="scheduled" />
        <StatusBadge status="completed" />
        <StatusBadge status="lifted" />
      </>
    );
    expect(screen.getByText("Просрочен")).toBeInTheDocument();
    expect(screen.getByText("Истекает")).toBeInTheDocument();
    expect(screen.getByText("Отсутствует")).toBeInTheDocument();
    expect(screen.getByText("Запланировано")).toBeInTheDocument();
    expect(screen.getByText("Завершено")).toBeInTheDocument();
    expect(screen.getByText("Снято")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Из `frontend/`: `npx vitest run src/components/common/StatusBadge.test.tsx`
Expected: FAIL — на экране сырые значения `overdue`, `due_soon`, … вместо RU-лейблов.

- [ ] **Step 3: Write minimal implementation**

В `frontend/src/components/common/StatusBadge.tsx`:

В `statusColors` (после строки `issued: "default",`) добавить:

```ts
  overdue: "destructive",
  missing: "destructive",
  due_soon: "secondary",
  scheduled: "secondary",
  completed: "default",
  lifted: "secondary",
```

В `statusLabelsRu` (после строки `issued: "Выдан",`) добавить:

```ts
  overdue: "Просрочен",
  due_soon: "Истекает",
  missing: "Отсутствует",
  scheduled: "Запланировано",
  completed: "Завершено",
  lifted: "Снято",
```

Примечание: `ready`/`cancelled`/`ok`/`active` уже есть в словарях — НЕ дублировать. Бонус: существующий бейдж «overdue» в реестре осмотров MedicalPage начнёт показывать «Просрочен» вместо сырого значения.

- [ ] **Step 4: Run test to verify it passes**

Из `frontend/`: `npx vitest run src/components/common/StatusBadge.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/common/StatusBadge.tsx frontend/src/components/common/StatusBadge.test.tsx
git commit -m "feat(p10-03): StatusBadge labels for contingent/referral/suspension statuses"
```

---

### Task 3: MedicalPage — сводка в шапке + секция «Контингент медосмотров»

**Files:**
- Modify: `frontend/src/pages/medical/MedicalPage.tsx`
- Modify: `frontend/src/pages/medical/MedicalPage.test.tsx`

**Контекст:** страница сейчас — `useAsyncResource` `data` (exams/persons/tasks) + `psych` + `RegistryPageHeader` + `RegistryTable` осмотров + секция психиатрии. Новые секции вставляются ПОСЛЕ блока `RegistryTable` (закрывается `) : null}` перед `<section …>` психиатрии) и ПЕРЕД секцией психиатрии.

- [ ] **Step 1: Write the failing tests**

В `frontend/src/pages/medical/MedicalPage.test.tsx` — ЗАМЕНИТЬ блок `vi.mock` и `beforeEach` на полный мок (страница на маунте зовёт все методы — неполный мок даст `undefined()`; грабли `OpsPages.test.tsx`):

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import MedicalPage from "./MedicalPage";
import { operationsApi } from "@/api/operations";

vi.mock("@/api/operations", () => ({
  operationsApi: {
    getMedicalSnapshot: vi.fn(),
    getPsychiatricSnapshot: vi.fn(),
    seedPsychiatricDefaults: vi.fn(),
    getMedicalOversightSnapshot: vi.fn(),
    downloadContingentRegisterPrint: vi.fn(),
    downloadNamedListPrint: vi.fn(),
    listMedicalReferrals: vi.fn(),
    createMedicalReferral: vi.fn(),
    transitionMedicalReferral: vi.fn(),
    generateMedicalReferrals: vi.fn(),
    listMedicalSuspensions: vi.fn(),
    liftMedicalSuspension: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  (operationsApi.getMedicalSnapshot as any).mockResolvedValue({
    exams: [
      {
        id: "e1",
        person_id: "p1",
        exam_type: "periodic",
        exam_date: "2026-01-10",
        conclusion: null,
        valid_until: "2027-01-10",
        created_at: "2026-01-10T00:00:00Z",
        updated_at: "2026-01-10T00:00:00Z",
      },
    ],
    persons: [
      { id: "p1", full_name: "Иванов Иван", status: "active" },
      { id: "p2", full_name: "Петров Пётр", status: "active" },
    ],
    tasks: [],
  });
  (operationsApi.getPsychiatricSnapshot as any).mockResolvedValue({
    activityTypes: [{ id: "a1", code: "height", name: "Работы на высоте", interval_days: 1825 }],
    contingent: [],
  });
  (operationsApi.seedPsychiatricDefaults as any).mockResolvedValue({ count: 9 });
  (operationsApi.getMedicalOversightSnapshot as any).mockResolvedValue({
    summary: { by_status: { ok: 1, overdue: 2 }, total: 5, overdue_count: 2, suspended_count: 1 },
    register: [
      {
        position_id: "pos1",
        position_name: "Электромонтёр",
        factors: [{ code: "4.1", name: "Электрополе" }],
        headcount: 3,
        exam_kinds: ["periodic", "psychiatric"],
        periodicity_months: 12,
      },
    ],
    namedList: [
      {
        person_id: "p1",
        full_name: "Иванов Иван",
        position_name: "Электромонтёр",
        department: "Цех 1",
        factors: [{ code: "4.1", name: "Электрополе" }],
        required_kinds: ["periodic"],
        last_exam_date: "2026-01-10",
        next_due_date: "2027-01-10",
        status: "overdue",
      },
    ],
  });
  (operationsApi.downloadContingentRegisterPrint as any).mockResolvedValue(undefined);
  (operationsApi.downloadNamedListPrint as any).mockResolvedValue(undefined);
  (operationsApi.listMedicalReferrals as any).mockResolvedValue([]);
  (operationsApi.createMedicalReferral as any).mockResolvedValue({ id: "r-new" });
  (operationsApi.transitionMedicalReferral as any).mockResolvedValue({ id: "r1", status: "scheduled" });
  (operationsApi.generateMedicalReferrals as any).mockResolvedValue({ count: 4 });
  (operationsApi.listMedicalSuspensions as any).mockResolvedValue([]);
  (operationsApi.liftMedicalSuspension as any).mockResolvedValue({ id: "s1", status: "lifted" });
});
```

Существующие 2 теста психиатрии оставить как есть (второй тест переопределяет `getPsychiatricSnapshot` — не мешает). Добавить новый describe:

```tsx
describe("MedicalPage contingent section", () => {
  it("renders summary stats and the register view by default", async () => {
    render(<MedicalPage />);
    await waitFor(() => expect(screen.getByText("Контингент медосмотров")).toBeInTheDocument());
    expect(screen.getByText("Позиций контингента")).toBeInTheDocument();
    expect(await screen.findByText("Электромонтёр")).toBeInTheDocument();
    expect(screen.getByText(/Электрополе/)).toBeInTheDocument();
  });

  it("switches to the named list view", async () => {
    render(<MedicalPage />);
    const btn = await screen.findByRole("button", { name: "Поимённый список" });
    fireEvent.click(btn);
    expect(await screen.findByText("Цех 1")).toBeInTheDocument();
    expect(screen.getByText("Просрочен")).toBeInTheDocument();
  });

  it("downloads the register print form for the active view", async () => {
    render(<MedicalPage />);
    const pdfBtn = await screen.findByRole("button", { name: "PDF" });
    fireEvent.click(pdfBtn);
    await waitFor(() => expect(operationsApi.downloadContingentRegisterPrint).toHaveBeenCalledWith("pdf"));
    fireEvent.click(screen.getByRole("button", { name: "Поимённый список" }));
    fireEvent.click(screen.getByRole("button", { name: "DOCX" }));
    await waitFor(() => expect(operationsApi.downloadNamedListPrint).toHaveBeenCalledWith("docx"));
  });

  it("shows a print error when the renderer is unavailable", async () => {
    (operationsApi.downloadContingentRegisterPrint as any).mockRejectedValue({ status: 503, message: "PDF converter is unavailable" });
    render(<MedicalPage />);
    const pdfBtn = await screen.findByRole("button", { name: "PDF" });
    fireEvent.click(pdfBtn);
    expect(await screen.findByText(/PDF converter is unavailable/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Из `frontend/`: `npx vitest run src/pages/medical/MedicalPage.test.tsx`
Expected: FAIL — 4 новых теста красные («Контингент медосмотров» не найден); 2 старых зелёные.

- [ ] **Step 3: Write the implementation**

В `frontend/src/pages/medical/MedicalPage.tsx`:

3a. Заменить импорты (полный новый блок импортов файла):

```tsx
import { useCallback, useMemo, useState } from "react";

import {
  operationsApi,
  type ContingentRegisterRowDto,
  type MedicalSummaryDto,
  type NamedListRowDto
} from "@/api/operations";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { RegistryTable } from "@/components/common/RegistryTable";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import { useLocalRegistry } from "@/hooks/useLocalRegistry";
import { formatDate } from "@/utils/datetime";
```

3b. Добавить модульные константы сразу после импортов (до `const MedicalPage`):

```tsx
const EXAM_KIND_LABELS: Record<string, string> = {
  periodic: "Периодический",
  preliminary: "Предварительный",
  psychiatric: "Психиатрическое (342н)",
  fluorography: "Флюорография",
  health_book: "Медкнижка"
};

const examKindLabel = (kind: string) => EXAM_KIND_LABELS[kind] ?? kind;

const mutationErrorText = (err: unknown, fallback: string) =>
  (err as { message?: string })?.message ?? fallback;
```

3c. Внутри компонента, после блока `psych`/`onSeed`, добавить oversight-ресурс и состояние секции контингента:

```tsx
  const oversight = useAsyncResource({
    loader: useCallback(() => operationsApi.getMedicalOversightSnapshot(), []),
    initialData: {
      summary: null as MedicalSummaryDto | null,
      register: [] as ContingentRegisterRowDto[],
      namedList: [] as NamedListRowDto[]
    },
    errorMessage: "Не удалось загрузить контингент медосмотров"
  });

  const [contingentView, setContingentView] = useState<"register" | "named">("register");
  const [printError, setPrintError] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);

  const onPrint = useCallback(
    async (fmt: "docx" | "pdf") => {
      setPrinting(true);
      setPrintError(null);
      try {
        if (contingentView === "register") {
          await operationsApi.downloadContingentRegisterPrint(fmt);
        } else {
          await operationsApi.downloadNamedListPrint(fmt);
        }
      } catch (err) {
        setPrintError(mutationErrorText(err, "Не удалось сформировать печатную форму"));
      } finally {
        setPrinting(false);
      }
    },
    [contingentView]
  );
```

3d. Заменить `stats` в `RegistryPageHeader` (убрать клиентские подсчёты по exams):

```tsx
        stats={[
          { label: "Позиций контингента", value: oversight.data.summary?.total ?? "—" },
          { label: "Просрочено/отсутствует", value: oversight.data.summary?.overdue_count ?? "—" },
          { label: "Активных отстранений", value: oversight.data.summary?.suspended_count ?? "—" }
        ]}
```

3e. Вставить секцию ПОСЛЕ закрывающего `) : null}` блока `RegistryTable` и ПЕРЕД `<section …>` психиатрии:

```tsx
      <section className="rounded-lg border border-border p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">Контингент медосмотров</h2>
            <p className="text-sm text-muted-foreground">Реестр по должностям (29н/342н) и поимённый список; печатные формы DOCX/PDF.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={`rounded-md border px-3 py-1.5 text-sm ${contingentView === "register" ? "border-primary font-medium" : "border-border"}`}
              onClick={() => setContingentView("register")}
            >
              По должностям
            </button>
            <button
              type="button"
              className={`rounded-md border px-3 py-1.5 text-sm ${contingentView === "named" ? "border-primary font-medium" : "border-border"}`}
              onClick={() => setContingentView("named")}
            >
              Поимённый список
            </button>
            <button type="button" className="rounded-md border border-border px-3 py-1.5 text-sm" onClick={() => void onPrint("docx")} disabled={printing}>
              DOCX
            </button>
            <button type="button" className="rounded-md border border-border px-3 py-1.5 text-sm" onClick={() => void onPrint("pdf")} disabled={printing}>
              PDF
            </button>
          </div>
        </div>
        <ErrorState error={oversight.error ?? undefined} onRetry={() => void oversight.reload()} />
        {printError ? <p className="text-sm text-destructive">{printError}</p> : null}
        {contingentView === "register" ? (
          oversight.data.register.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Должность</TableHead>
                  <TableHead>Численность</TableHead>
                  <TableHead>Факторы</TableHead>
                  <TableHead>Виды осмотров</TableHead>
                  <TableHead>Периодичность, мес</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {oversight.data.register.map((row) => (
                  <TableRow key={row.position_id}>
                    <TableCell>{row.position_name}</TableCell>
                    <TableCell>{row.headcount}</TableCell>
                    <TableCell>{row.factors.map((f) => `${f.code} — ${f.name}`).join(", ") || "—"}</TableCell>
                    <TableCell>{row.exam_kinds.map(examKindLabel).join(", ")}</TableCell>
                    <TableCell>{row.periodicity_months ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">Контингент пуст — настройте нормы и факторы.</p>
          )
        ) : oversight.data.namedList.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ФИО</TableHead>
                <TableHead>Должность</TableHead>
                <TableHead>Подразделение</TableHead>
                <TableHead>Виды осмотров</TableHead>
                <TableHead>Последний осмотр</TableHead>
                <TableHead>Следующий</TableHead>
                <TableHead>Статус</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {oversight.data.namedList.map((row) => (
                <TableRow key={row.person_id}>
                  <TableCell>{row.full_name}</TableCell>
                  <TableCell>{row.position_name ?? "—"}</TableCell>
                  <TableCell>{row.department ?? "—"}</TableCell>
                  <TableCell>{row.required_kinds.map(examKindLabel).join(", ")}</TableCell>
                  <TableCell>{row.last_exam_date ? formatDate(row.last_exam_date) : "—"}</TableCell>
                  <TableCell>{row.next_due_date ? formatDate(row.next_due_date) : "—"}</TableCell>
                  <TableCell>
                    <StatusBadge status={row.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-sm text-muted-foreground">Поимённый список пуст.</p>
        )}
      </section>
```

- [ ] **Step 4: Run tests to verify they pass**

Из `frontend/`: `npx vitest run src/pages/medical/MedicalPage.test.tsx`
Expected: PASS (2 старых + 4 новых).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/medical/MedicalPage.tsx frontend/src/pages/medical/MedicalPage.test.tsx
git commit -m "feat(p10-03): MedicalPage summary stats + contingent section (register/named list/print)"
```

---

### Task 4: Секция «Направления» — список, фильтр, генерация, создание, простые переходы

**Files:**
- Modify: `frontend/src/pages/medical/MedicalPage.tsx`
- Modify: `frontend/src/pages/medical/MedicalPage.test.tsx`

- [ ] **Step 1: Write the failing tests**

Добавить в `MedicalPage.test.tsx` describe:

```tsx
describe("MedicalPage referrals section", () => {
  it("renders referrals with resolved person names and statuses", async () => {
    (operationsApi.listMedicalReferrals as any).mockResolvedValue([
      { id: "r1", person_id: "p1", exam_kind: "periodic", due_at: "2026-08-01", status: "issued", medical_org_name: "Клиника", result_exam_id: null, is_overdue: false },
    ]);
    render(<MedicalPage />);
    await waitFor(() => expect(screen.getByText("Направления на медосмотры")).toBeInTheDocument());
    expect(await screen.findByText("Выдан")).toBeInTheDocument();
    expect(screen.getAllByText(/Иванов Иван/).length).toBeGreaterThan(0);
    expect(screen.getByText("Клиника")).toBeInTheDocument();
  });

  it("generates referrals by contingent and reloads the list", async () => {
    render(<MedicalPage />);
    const btn = await screen.findByRole("button", { name: "Сформировать по контингенту" });
    fireEvent.click(btn);
    await waitFor(() => expect(operationsApi.generateMedicalReferrals).toHaveBeenCalled());
    expect(await screen.findByText("Создано направлений: 4")).toBeInTheDocument();
    expect((operationsApi.listMedicalReferrals as any).mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("creates a manual referral with the selected person and kind", async () => {
    render(<MedicalPage />);
    const personSelect = await screen.findByLabelText("Сотрудник для направления");
    fireEvent.change(personSelect, { target: { value: "p2" } });
    fireEvent.change(screen.getByLabelText("Вид осмотра"), { target: { value: "psychiatric" } });
    fireEvent.click(screen.getByRole("button", { name: "Создать направление" }));
    await waitFor(() =>
      expect(operationsApi.createMedicalReferral).toHaveBeenCalledWith({
        person_id: "p2",
        exam_kind: "psychiatric",
      })
    );
  });

  it("filters referrals by status server-side", async () => {
    render(<MedicalPage />);
    const filter = await screen.findByLabelText("Фильтр по статусу направления");
    fireEvent.change(filter, { target: { value: "scheduled" } });
    await waitFor(() =>
      expect(operationsApi.listMedicalReferrals).toHaveBeenLastCalledWith({ status: "scheduled" })
    );
  });

  it("schedules and cancels an issued referral", async () => {
    (operationsApi.listMedicalReferrals as any).mockResolvedValue([
      { id: "r1", person_id: "p1", exam_kind: "periodic", due_at: null, status: "issued", medical_org_name: null, result_exam_id: null, is_overdue: false },
    ]);
    render(<MedicalPage />);
    const scheduleBtn = await screen.findByRole("button", { name: "Запланировать" });
    fireEvent.click(scheduleBtn);
    await waitFor(() =>
      expect(operationsApi.transitionMedicalReferral).toHaveBeenCalledWith("r1", { to: "scheduled" })
    );
    const cancelBtn = await screen.findByRole("button", { name: "Отменить" });
    fireEvent.click(cancelBtn);
    await waitFor(() =>
      expect(operationsApi.transitionMedicalReferral).toHaveBeenCalledWith("r1", { to: "cancelled" })
    );
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Из `frontend/`: `npx vitest run src/pages/medical/MedicalPage.test.tsx`
Expected: FAIL — 5 новых красные, прежние зелёные.

- [ ] **Step 3: Write the implementation**

В `MedicalPage.tsx`:

3a. Дополнить импорт из `@/api/operations` типом `MedicalReferralDto`:

```tsx
import {
  operationsApi,
  type ContingentRegisterRowDto,
  type MedicalReferralDto,
  type MedicalSummaryDto,
  type NamedListRowDto
} from "@/api/operations";
```

3b. Внутри компонента (после блока `onPrint`) добавить состояние/хендлеры направлений:

```tsx
  const [referralStatusFilter, setReferralStatusFilter] = useState("");
  const referrals = useAsyncResource({
    loader: useCallback(
      () => operationsApi.listMedicalReferrals(referralStatusFilter ? { status: referralStatusFilter } : undefined),
      [referralStatusFilter]
    ),
    initialData: [] as MedicalReferralDto[],
    errorMessage: "Не удалось загрузить направления"
  });
  const [referralError, setReferralError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generatedCount, setGeneratedCount] = useState<number | null>(null);
  const [creatingReferral, setCreatingReferral] = useState(false);
  const [newReferral, setNewReferral] = useState({ person_id: "", exam_kind: "periodic", due_at: "", medical_org_name: "" });
  const [transitioningId, setTransitioningId] = useState<string | null>(null);

  const personName = useMemo(() => {
    const map = new Map<string, string>();
    data.persons.forEach((person) => map.set(person.id, person.full_name));
    return (id: string) => map.get(id) ?? id;
  }, [data.persons]);

  const onGenerateReferrals = useCallback(async () => {
    setGenerating(true);
    setReferralError(null);
    setGeneratedCount(null);
    try {
      const { count } = await operationsApi.generateMedicalReferrals();
      setGeneratedCount(count);
      await referrals.reload();
    } catch (err) {
      setReferralError(mutationErrorText(err, "Не удалось сформировать направления"));
    } finally {
      setGenerating(false);
    }
  }, [referrals]);

  const onCreateReferral = useCallback(async () => {
    if (!newReferral.person_id) return;
    setCreatingReferral(true);
    setReferralError(null);
    try {
      await operationsApi.createMedicalReferral({
        person_id: newReferral.person_id,
        exam_kind: newReferral.exam_kind,
        ...(newReferral.due_at ? { due_at: newReferral.due_at } : {}),
        ...(newReferral.medical_org_name.trim() ? { medical_org_name: newReferral.medical_org_name.trim() } : {})
      });
      setNewReferral({ person_id: "", exam_kind: "periodic", due_at: "", medical_org_name: "" });
      await referrals.reload();
    } catch (err) {
      setReferralError(mutationErrorText(err, "Не удалось создать направление"));
    } finally {
      setCreatingReferral(false);
    }
  }, [newReferral, referrals]);

  const onTransitionReferral = useCallback(
    async (referralId: string, to: string, resultExamId?: string) => {
      setTransitioningId(referralId);
      setReferralError(null);
      try {
        await operationsApi.transitionMedicalReferral(referralId, {
          to,
          ...(resultExamId ? { result_exam_id: resultExamId } : {})
        });
        await referrals.reload();
      } catch (err) {
        setReferralError(mutationErrorText(err, "Не удалось изменить статус направления"));
      } finally {
        setTransitioningId(null);
      }
    },
    [referrals]
  );
```

3c. Вставить секцию ПОСЛЕ секции «Контингент медосмотров» (перед секцией психиатрии):

```tsx
      <section className="rounded-lg border border-border p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">Направления на медосмотры</h2>
            <p className="text-sm text-muted-foreground">Выдача направлений вручную или по контингенту; статусы: выдан → запланирован → завершён/отменён.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Фильтр по статусу направления"
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={referralStatusFilter}
              onChange={(e) => setReferralStatusFilter(e.target.value)}
            >
              <option value="">Все статусы</option>
              <option value="issued">Выдан</option>
              <option value="scheduled">Запланировано</option>
              <option value="completed">Завершено</option>
              <option value="cancelled">Отменено</option>
            </select>
            <button
              type="button"
              className="rounded-md border border-border px-3 py-1.5 text-sm"
              onClick={() => void onGenerateReferrals()}
              disabled={generating}
            >
              {generating ? "Формирование…" : "Сформировать по контингенту"}
            </button>
          </div>
        </div>
        <ErrorState error={referrals.error ?? undefined} onRetry={() => void referrals.reload()} />
        {referralError ? <p className="text-sm text-destructive">{referralError}</p> : null}
        {generatedCount !== null ? <p className="text-sm">Создано направлений: {generatedCount}</p> : null}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <select
            aria-label="Сотрудник для направления"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={newReferral.person_id}
            onChange={(e) => setNewReferral((f) => ({ ...f, person_id: e.target.value }))}
          >
            <option value="">Сотрудник…</option>
            {data.persons.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
              </option>
            ))}
          </select>
          <select
            aria-label="Вид осмотра"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={newReferral.exam_kind}
            onChange={(e) => setNewReferral((f) => ({ ...f, exam_kind: e.target.value }))}
          >
            {Object.entries(EXAM_KIND_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <input
            aria-label="Срок направления"
            type="date"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={newReferral.due_at}
            onChange={(e) => setNewReferral((f) => ({ ...f, due_at: e.target.value }))}
          />
          <input
            aria-label="Медорганизация"
            placeholder="Медорганизация (опционально)"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={newReferral.medical_org_name}
            onChange={(e) => setNewReferral((f) => ({ ...f, medical_org_name: e.target.value }))}
          />
        </div>
        <button
          type="button"
          className="rounded-md border border-border px-3 py-1.5 text-sm"
          onClick={() => void onCreateReferral()}
          disabled={creatingReferral || !newReferral.person_id}
        >
          Создать направление
        </button>
        {referrals.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Сотрудник</TableHead>
                <TableHead>Вид</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Срок</TableHead>
                <TableHead>Медорганизация</TableHead>
                <TableHead>Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {referrals.data.map((referral) => (
                <TableRow key={referral.id}>
                  <TableCell>{personName(referral.person_id)}</TableCell>
                  <TableCell>{examKindLabel(referral.exam_kind)}</TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1">
                      <StatusBadge status={referral.status} />
                      {referral.is_overdue && referral.status !== "completed" && referral.status !== "cancelled" ? (
                        <span className="text-xs text-destructive">Просрочено</span>
                      ) : null}
                    </span>
                  </TableCell>
                  <TableCell>{referral.due_at ? formatDate(referral.due_at) : "—"}</TableCell>
                  <TableCell>{referral.medical_org_name ?? "—"}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-2">
                      {referral.status === "issued" ? (
                        <button
                          type="button"
                          className="rounded-md border border-border px-2 py-1 text-xs"
                          onClick={() => void onTransitionReferral(referral.id, "scheduled")}
                          disabled={transitioningId === referral.id}
                        >
                          Запланировать
                        </button>
                      ) : null}
                      {referral.status === "issued" || referral.status === "scheduled" ? (
                        <button
                          type="button"
                          className="rounded-md border border-border px-2 py-1 text-xs"
                          onClick={() => void onTransitionReferral(referral.id, "cancelled")}
                          disabled={transitioningId === referral.id}
                        >
                          Отменить
                        </button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-sm text-muted-foreground">Направлений нет.</p>
        )}
      </section>
```

- [ ] **Step 4: Run tests to verify they pass**

Из `frontend/`: `npx vitest run src/pages/medical/MedicalPage.test.tsx`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/medical/MedicalPage.tsx frontend/src/pages/medical/MedicalPage.test.tsx
git commit -m "feat(p10-03): MedicalPage referrals section (list/filter/generate/create/schedule/cancel)"
```

---

### Task 5: «Завершить» направление — выбор осмотра-результата

**Files:**
- Modify: `frontend/src/pages/medical/MedicalPage.tsx`
- Modify: `frontend/src/pages/medical/MedicalPage.test.tsx`

**Backend-контракт:** `POST /medical/referrals/{id}/transition {to: "completed"}` без `result_exam_id` → 422; осмотр должен принадлежать тому же person (иначе 404/422 от backend).

- [ ] **Step 1: Write the failing tests**

Добавить describe:

```tsx
describe("MedicalPage referral completion", () => {
  it("completes a scheduled referral with a selected result exam", async () => {
    (operationsApi.listMedicalReferrals as any).mockResolvedValue([
      { id: "r1", person_id: "p1", exam_kind: "periodic", due_at: null, status: "scheduled", medical_org_name: null, result_exam_id: null, is_overdue: false },
    ]);
    render(<MedicalPage />);
    const completeBtn = await screen.findByRole("button", { name: "Завершить" });
    fireEvent.click(completeBtn);
    const examSelect = await screen.findByLabelText("Осмотр-результат");
    const confirmBtn = screen.getByRole("button", { name: "Подтвердить" });
    expect(confirmBtn).toBeDisabled();
    fireEvent.change(examSelect, { target: { value: "e1" } });
    expect(confirmBtn).not.toBeDisabled();
    fireEvent.click(confirmBtn);
    await waitFor(() =>
      expect(operationsApi.transitionMedicalReferral).toHaveBeenCalledWith("r1", { to: "completed", result_exam_id: "e1" })
    );
  });

  it("shows a hint instead of the picker when the person has no exams", async () => {
    (operationsApi.listMedicalReferrals as any).mockResolvedValue([
      { id: "r2", person_id: "p2", exam_kind: "periodic", due_at: null, status: "scheduled", medical_org_name: null, result_exam_id: null, is_overdue: false },
    ]);
    render(<MedicalPage />);
    const completeBtn = await screen.findByRole("button", { name: "Завершить" });
    fireEvent.click(completeBtn);
    expect(await screen.findByText("Сначала зафиксируйте осмотр в реестре выше.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Осмотр-результат")).not.toBeInTheDocument();
  });
});
```

(В beforeEach exams содержит единственный осмотр `e1` person'а `p1`; у `p2` осмотров нет.)

- [ ] **Step 2: Run tests to verify they fail**

Из `frontend/`: `npx vitest run src/pages/medical/MedicalPage.test.tsx`
Expected: FAIL — кнопки «Завершить» нет.

- [ ] **Step 3: Write the implementation**

В `MedicalPage.tsx`:

3a. Добавить состояние (рядом с `transitioningId`):

```tsx
  const [completingId, setCompletingId] = useState<string | null>(null);
  const [resultExamId, setResultExamId] = useState("");
```

3b. В хендлере `onTransitionReferral` после успешного `reload()` добавить сброс (полный новый try-блок):

```tsx
      try {
        await operationsApi.transitionMedicalReferral(referralId, {
          to,
          ...(resultExamId ? { result_exam_id: resultExamId } : {})
        });
        setCompletingId(null);
        setResultExamId("");
        await referrals.reload();
      } catch (err) {
```

ВНИМАНИЕ: параметр хендлера называется `resultExamId` и state-переменная тоже — конфликт имён. Переименовать ПАРАМЕТР хендлера в `resultExam`:

```tsx
  const onTransitionReferral = useCallback(
    async (referralId: string, to: string, resultExam?: string) => {
      setTransitioningId(referralId);
      setReferralError(null);
      try {
        await operationsApi.transitionMedicalReferral(referralId, {
          to,
          ...(resultExam ? { result_exam_id: resultExam } : {})
        });
        setCompletingId(null);
        setResultExamId("");
        await referrals.reload();
      } catch (err) {
        setReferralError(mutationErrorText(err, "Не удалось изменить статус направления"));
      } finally {
        setTransitioningId(null);
      }
    },
    [referrals]
  );
```

3c. В ячейке «Действия» таблицы направлений добавить кнопку «Завершить» для `scheduled` (внутрь `div.flex`, перед кнопкой «Отменить»):

```tsx
                      {referral.status === "scheduled" ? (
                        <button
                          type="button"
                          className="rounded-md border border-border px-2 py-1 text-xs"
                          onClick={() => {
                            setCompletingId((current) => (current === referral.id ? null : referral.id));
                            setResultExamId("");
                          }}
                          disabled={transitioningId === referral.id}
                        >
                          Завершить
                        </button>
                      ) : null}
```

3d. Там же, после `div.flex` с кнопками (внутри той же `TableCell`), добавить раскрывающийся выбор осмотра:

```tsx
                    {completingId === referral.id ? (
                      (() => {
                        const personExams = data.exams.filter((exam) => exam.person_id === referral.person_id);
                        if (personExams.length === 0) {
                          return <p className="mt-2 text-xs text-muted-foreground">Сначала зафиксируйте осмотр в реестре выше.</p>;
                        }
                        return (
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <select
                              aria-label="Осмотр-результат"
                              className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                              value={resultExamId}
                              onChange={(e) => setResultExamId(e.target.value)}
                            >
                              <option value="">Выберите осмотр…</option>
                              {personExams.map((exam) => (
                                <option key={exam.id} value={exam.id}>
                                  {examKindLabel(exam.exam_type)} · {formatDate(exam.exam_date)}
                                </option>
                              ))}
                            </select>
                            <button
                              type="button"
                              className="rounded-md border border-border px-2 py-1 text-xs"
                              onClick={() => void onTransitionReferral(referral.id, "completed", resultExamId)}
                              disabled={!resultExamId || transitioningId === referral.id}
                            >
                              Подтвердить
                            </button>
                          </div>
                        );
                      })()
                    ) : null}
```

- [ ] **Step 4: Run tests to verify they pass**

Из `frontend/`: `npx vitest run src/pages/medical/MedicalPage.test.tsx`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/medical/MedicalPage.tsx frontend/src/pages/medical/MedicalPage.test.tsx
git commit -m "feat(p10-03): complete referral with result exam picker"
```

---

### Task 6: Секция «Отстранения» — список, фильтр «только активные», lift

**Files:**
- Modify: `frontend/src/pages/medical/MedicalPage.tsx`
- Modify: `frontend/src/pages/medical/MedicalPage.test.tsx`

- [ ] **Step 1: Write the failing tests**

Добавить describe:

```tsx
describe("MedicalPage suspensions section", () => {
  it("renders suspensions with reason labels and source exam", async () => {
    (operationsApi.listMedicalSuspensions as any).mockResolvedValue([
      { id: "s1", person_id: "p1", reason: "unfit", status: "active", source_exam_id: "e1" },
    ]);
    render(<MedicalPage />);
    await waitFor(() => expect(screen.getByText("Отстранения от работы")).toBeInTheDocument());
    expect(await screen.findByText("Негоден")).toBeInTheDocument();
    expect(operationsApi.listMedicalSuspensions).toHaveBeenCalledWith({ status: "active" });
  });

  it("lifts an active suspension after confirmation and reloads", async () => {
    (operationsApi.listMedicalSuspensions as any).mockResolvedValue([
      { id: "s1", person_id: "p1", reason: "unfit", status: "active", source_exam_id: null },
    ]);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MedicalPage />);
    const liftBtn = await screen.findByRole("button", { name: "Снять отстранение" });
    fireEvent.click(liftBtn);
    await waitFor(() => expect(operationsApi.liftMedicalSuspension).toHaveBeenCalledWith("s1"));
    expect((operationsApi.getMedicalOversightSnapshot as any).mock.calls.length).toBeGreaterThanOrEqual(2);
    confirmSpy.mockRestore();
  });

  it("does not lift when the confirmation is dismissed", async () => {
    (operationsApi.listMedicalSuspensions as any).mockResolvedValue([
      { id: "s1", person_id: "p1", reason: "unfit", status: "active", source_exam_id: null },
    ]);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<MedicalPage />);
    const liftBtn = await screen.findByRole("button", { name: "Снять отстранение" });
    fireEvent.click(liftBtn);
    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(operationsApi.liftMedicalSuspension).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("loads all suspensions when the active-only toggle is unchecked", async () => {
    render(<MedicalPage />);
    const toggle = await screen.findByLabelText("Только активные");
    fireEvent.click(toggle);
    await waitFor(() => expect(operationsApi.listMedicalSuspensions).toHaveBeenLastCalledWith(undefined));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Из `frontend/`: `npx vitest run src/pages/medical/MedicalPage.test.tsx`
Expected: FAIL — секции «Отстранения от работы» нет.

- [ ] **Step 3: Write the implementation**

В `MedicalPage.tsx`:

3a. Добавить модульную константу (рядом с `EXAM_KIND_LABELS`):

```tsx
const SUSPENSION_REASON_LABELS: Record<string, string> = {
  unfit: "Негоден",
  contraindication: "Противопоказания"
};
```

3b. Дополнить импорт типом `MedicalSuspensionDto`:

```tsx
import {
  operationsApi,
  type ContingentRegisterRowDto,
  type MedicalReferralDto,
  type MedicalSummaryDto,
  type MedicalSuspensionDto,
  type NamedListRowDto
} from "@/api/operations";
```

3c. Состояние/хендлеры (после блока направлений):

```tsx
  const [suspensionsActiveOnly, setSuspensionsActiveOnly] = useState(true);
  const suspensions = useAsyncResource({
    loader: useCallback(
      () => operationsApi.listMedicalSuspensions(suspensionsActiveOnly ? { status: "active" } : undefined),
      [suspensionsActiveOnly]
    ),
    initialData: [] as MedicalSuspensionDto[],
    errorMessage: "Не удалось загрузить отстранения"
  });
  const [suspensionError, setSuspensionError] = useState<string | null>(null);
  const [liftingId, setLiftingId] = useState<string | null>(null);

  const examLabelById = useMemo(() => {
    const map = new Map<string, string>();
    data.exams.forEach((exam) => map.set(exam.id, `${examKindLabel(exam.exam_type)} · ${formatDate(exam.exam_date)}`));
    return (id: string | null | undefined) => (id ? map.get(id) ?? id : "—");
  }, [data.exams]);

  const onLiftSuspension = useCallback(
    async (suspensionId: string) => {
      if (!window.confirm("Снять отстранение? Работник будет допущен к работе.")) return;
      setLiftingId(suspensionId);
      setSuspensionError(null);
      try {
        await operationsApi.liftMedicalSuspension(suspensionId);
        await Promise.all([suspensions.reload(), oversight.reload()]);
      } catch (err) {
        setSuspensionError(mutationErrorText(err, "Не удалось снять отстранение"));
      } finally {
        setLiftingId(null);
      }
    },
    [oversight, suspensions]
  );
```

3d. Секция ПОСЛЕ секции «Направления на медосмотры» (перед психиатрией):

```tsx
      <section className="rounded-lg border border-border p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold">Отстранения от работы</h2>
            <p className="text-sm text-muted-foreground">Автоматические отстранения по результатам осмотров; снятие — только admin/owner.</p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              aria-label="Только активные"
              type="checkbox"
              checked={suspensionsActiveOnly}
              onChange={(e) => setSuspensionsActiveOnly(e.target.checked)}
            />
            Только активные
          </label>
        </div>
        <ErrorState error={suspensions.error ?? undefined} onRetry={() => void suspensions.reload()} />
        {suspensionError ? <p className="text-sm text-destructive">{suspensionError}</p> : null}
        {suspensions.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Сотрудник</TableHead>
                <TableHead>Причина</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Осмотр-источник</TableHead>
                <TableHead>Действие</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {suspensions.data.map((suspension) => (
                <TableRow key={suspension.id}>
                  <TableCell>{personName(suspension.person_id)}</TableCell>
                  <TableCell>{SUSPENSION_REASON_LABELS[suspension.reason] ?? suspension.reason}</TableCell>
                  <TableCell>
                    <StatusBadge status={suspension.status} />
                  </TableCell>
                  <TableCell>{examLabelById(suspension.source_exam_id)}</TableCell>
                  <TableCell>
                    {suspension.status === "active" ? (
                      <button
                        type="button"
                        className="rounded-md border border-border px-2 py-1 text-xs"
                        onClick={() => void onLiftSuspension(suspension.id)}
                        disabled={liftingId === suspension.id}
                      >
                        Снять отстранение
                      </button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-sm text-muted-foreground">Отстранений нет.</p>
        )}
      </section>
```

- [ ] **Step 4: Run tests to verify they pass**

Из `frontend/`: `npx vitest run src/pages/medical/MedicalPage.test.tsx`
Expected: PASS (17 tests).

- [ ] **Step 5: Run adjacent test files (регресс среза)**

Из `frontend/`:
`npx vitest run src/pages/medical/MedicalPage.test.tsx src/components/common/StatusBadge.test.tsx src/__tests__/medicalOversightApi.test.ts`
Expected: PASS все.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/medical/MedicalPage.tsx frontend/src/pages/medical/MedicalPage.test.tsx
git commit -m "feat(p10-03): MedicalPage suspensions section (active filter + lift with confirm)"
```

---

### Task 7: Полные фронт-гейты

**Files:** нет изменений (только прогоны; фиксы — если гейты красные).

- [ ] **Step 1: Полный vitest**

Из `frontend/`: `npx vitest run`
Expected: все зелёные. Таймаут инструмента 600000 мс. НЕ гонять параллельно с другими тяжёлыми процессами. При единичных красных НЕ из этого среза — перепроверить файл в изоляции (`npx vitest run <файл>`): зелёный в изоляции = флейк параллелизма, повторить полный прогон; красный в изоляции — чинить только если сломано ЭТИМ срезом (иначе зафиксировать в handoff как pre-existing).

- [ ] **Step 2: Typecheck**

`npm --prefix frontend run typecheck`
Expected: exit 0, ошибок 0.

- [ ] **Step 3: Build**

`npm --prefix frontend run build`
Expected: exit 0.

- [ ] **Step 4: Commit (только если были фиксы)**

```bash
git add -A
git commit -m "fix(p10-03): frontend gate fixes"
```

---

### Task 8: Документация + handoff

**Files:**
- Modify: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` (строка P10-03, ~655)
- Modify: `CHANGELOG.md` (новая запись сверху)
- Modify: `AI_IMPLEMENTATION_REPORT.md` (новый handoff-блок сверху)

- [ ] **Step 1: Роадмап**

В строке таблицы **P10-03** (`| **P10-03** | Медосмотры (полный контур) | …`):
- в колонку Evidence дописать (перед «**Остаётся:**»): `Фронт-контур на MedicalPage (ветка feat/p10-03-medical-oversight-ui): сводка /medical/summary в шапке; секция «Контингент медосмотров» (реестр по должностям + поимённый список + печать DOCX/PDF); секция «Направления» (фильтр по статусу, bulk-генерация по контингенту, ручное создание, FSM-переходы запланировать/отменить/завершить с привязкой осмотра-результата); секция «Отстранения» (фильтр «только активные», снятие с подтверждением).`
- из «**Остаётся:**» удалить пункт «фронт для контингента/направлений/отстранения (backend готов)», оставив «per-activity частичное ограничение; печатная форма направления/решения комиссии».

- [ ] **Step 2: CHANGELOG**

Добавить сверху запись (формат существующих):

```markdown
## 2026-07-09 — P10-03 Медосмотры: фронт контингента/направлений/отстранений

- `MedicalPage`: сводка `/medical/summary` в шапке; секция «Контингент медосмотров» — реестр по должностям и поимённый список с печатью DOCX/PDF; секция «Направления на медосмотры» — фильтр, bulk-генерация по контингенту, ручное создание, переходы FSM (запланировать/отменить/завершить с осмотром-результатом); секция «Отстранения от работы» — фильтр «только активные», снятие с подтверждением (RBAC на backend).
- `operationsApi`: 9 новых методов + 5 DTO; `StatusBadge`: RU-лейблы overdue/due_soon/missing/scheduled/completed/lifted.
- Чисто фронтовый срез: без миграций и изменений OpenAPI. Тесты: MedicalPage 17, StatusBadge 1, API 9.
```

- [ ] **Step 3: Handoff-блок**

В `AI_IMPLEMENTATION_REPORT.md` добавить новый блок «Last Agent Handoff (2026-07-09, P10-03 МЕДОСМОТРЫ — ФРОНТ КОНТИНГЕНТ/НАПРАВЛЕНИЯ/ОТСТРАНЕНИЯ — ветка feat/p10-03-medical-oversight-ui, НЕ влита)» ПЕРЕД текущим верхним блоком, по образцу предыдущих: дата/драйвер, решения brainstorming (4), «ГЛАВНОЕ» (чисто фронтовый срез, 0 backend), архитектура (API-методы/секции), верификация (числа прогонов), осознанно отложено (typeahead persons, печать направления, редактор маппинга 342н, пагинация), грабли/операционка, Next (следующий срез: P10-07 analytics ИЛИ §12.4 бюджетный контур ИЛИ P10-03 остатки).

- [ ] **Step 4: Commit**

```bash
git add docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md CHANGELOG.md AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(p10-03): roadmap + changelog + handoff for medical oversight UI"
```

---

## Self-Review (выполнен при написании плана)

- **Spec coverage:** шапка-stats (Task 3), контингент 2 представления + печать + 503 (Task 3), направления полный FSM включая completed+result_exam_id и подсказку без осмотров (Tasks 4-5), отстранения + lift + confirm + reload шапки (Task 6), API-слой + blob (Task 1), StatusBadge RU-лейблы (Task 2), гейты (Task 7), docs (Task 8). Пробелов нет.
- **Placeholders:** нет TBD/TODO; все шаги с полным кодом.
- **Type consistency:** `MedicalReferralDto.status` union совпадает с FSM; `onTransitionReferral(referralId, to, resultExam?)` — конфликт имён с state `resultExamId` разрешён в Task 5 3b; DTO-имена в тестах Task 1 совпадают с реализацией; мок-набор в Task 3 покрывает все 12 методов, которые страница зовёт на маунте.
