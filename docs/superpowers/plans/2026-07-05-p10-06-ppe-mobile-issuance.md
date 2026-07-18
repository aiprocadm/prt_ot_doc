# PPE Mobile Issuance (online-first cart) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a touch-first `/ppe/issue` page that lets an operator find a worker, build a cart of PPE items, and issue them all at once over the existing `POST /ppe/issues` API.

**Architecture:** Frontend-only slice. A `useMobileIssue` hook owns all state (data load, cart, submit); a single-file `MobileIssuePage` renders the three-step flow (worker → items → review). No backend, no migration, no new endpoints, no OpenAPI/PG changes. Issuance rides the already-complete `create_issue → deplete_for_issue` (FIFO) path, so the honest-stock invariant is untouched.

**Tech Stack:** React 18 + TypeScript + Vite, Zustand (`useAuthStore`), Radix/shadcn UI (`Button`, `Card`), `sonner` (not needed here — results render inline), `vitest` + `@testing-library/react` (`render`, `renderHook`, `fireEvent`, `waitFor`), react-router v6.

**Spec:** `docs/superpowers/specs/2026-07-05-p10-06-ppe-mobile-issuance-design.md`

---

## Conventions locked from the codebase (read before starting)

- **Pages are single files** and **hardcode Russian strings** (see `frontend/src/pages/ppe/PpePage.tsx`, `frontend/src/pages/warehouse/WarehousePage.tsx` at 995 lines). We follow that: one page file + a separate hook/types for the stateful core. **Do NOT add i18n** — no page in this layer uses it.
- **Routes:** lazy component in `frontend/src/router/pageRegistry.tsx`, re-exported into `frontend/src/router/routeGroups.tsx`’s barrel import, then a `{ permission, routes: [<Route/>] }` group.
- **Tests** live in `frontend/src/__tests__/`, mock API modules with `vi.mock("@/api/...")`, and (for permission-gated UI) set `useAuthStore.setState({...})`. See `PpePage.test.tsx`, `WarehousePage.test.tsx`, `usePagination.test.tsx`.
- **Error type:** `ApiError` from `@/types/dto/common` (has `.message`).
- **Run frontend gates from PowerShell** (worktree has no `.venv`; backend not involved here). Commands:
  - `npm --prefix frontend run test` (→ `vitest run`)
  - `npm --prefix frontend run typecheck` (→ `tsc --noEmit`)
  - `npm --prefix frontend run build` (→ `tsc --noEmit && vite build`)
  - Single test file: `npm --prefix frontend exec vitest run src/__tests__/useMobileIssue.test.tsx`
- **No backend gates:** do NOT re-snapshot OpenAPI, do NOT run the PG16 gate, do NOT run ruff/black (no `.py` touched).

## File structure

| File | Responsibility | Task |
|---|---|---|
| `frontend/src/pages/ppe/mobile-issue/types.ts` | Shared types: `MobileIssueStep`, `CartLine`, `IssueResultLine` | 1 |
| `frontend/src/pages/ppe/mobile-issue/useMobileIssue.ts` | Hook: data load (+silent stock degrade), worker/cart state, `issueAll` with partial-failure + double-tap guard | 1 |
| `frontend/src/__tests__/useMobileIssue.test.tsx` | Unit tests (renderHook) for all hook logic | 1 |
| `frontend/src/router/pageRegistry.tsx` | Add lazy `MobileIssuePage` export | 2 |
| `frontend/src/router/routeGroups.tsx` | Import + route group `/ppe/issue` gated by `PPE_ISSUE` | 2 |
| `frontend/src/pages/ppe/MobileIssuePage.tsx` | Single-file page: three-step UI wired to the hook | 2,3,4 |
| `frontend/src/__tests__/MobileIssuePage.test.tsx` | Page-level flow tests | 2,3,4 |
| `frontend/src/pages/ppe/PpePage.tsx` | Add "Мобильная выдача" entry-point button | 5 |
| `frontend/src/__tests__/PpePage.test.tsx` | Assert entry-point button/link | 5 |
| `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, `CHANGELOG.md`, `AI_IMPLEMENTATION_REPORT.md` | Docs update | 6 |

---

## Task 1: Hook + types (all state logic, unit-tested)

**Files:**
- Create: `frontend/src/pages/ppe/mobile-issue/types.ts`
- Create: `frontend/src/pages/ppe/mobile-issue/useMobileIssue.ts`
- Test: `frontend/src/__tests__/useMobileIssue.test.tsx`

- [ ] **Step 1: Create the types file**

`frontend/src/pages/ppe/mobile-issue/types.ts`:

```ts
export type MobileIssueStep = "worker" | "items" | "review";

export type CartLine = {
  item_id: string;
  item_name: string;
  quantity: number;
  on_hand: number | null; // null = stock unknown (warehouse flag off / no data)
};

export type IssueResultLine = {
  item_id: string;
  item_name: string;
  quantity: number;
  status: "ok" | "error";
  error?: string;
};
```

- [ ] **Step 2: Write the failing hook test**

`frontend/src/__tests__/useMobileIssue.test.tsx`:

```tsx
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useMobileIssue } from "@/pages/ppe/mobile-issue/useMobileIssue";

const getPpeOverviewMock = vi.fn();
const createPpeIssueMock = vi.fn();
const listLevelsMock = vi.fn();

vi.mock("@/api/ops", () => ({
  opsApi: {
    getPpeOverview: (...a: unknown[]) => getPpeOverviewMock(...a),
    createPpeIssue: (...a: unknown[]) => createPpeIssueMock(...a)
  }
}));

vi.mock("@/api/warehouse", () => ({
  warehouseApi: {
    listLevels: (...a: unknown[]) => listLevelsMock(...a)
  }
}));

const person = (id: string, full_name: string, status = "active") => ({
  id,
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  first_name: full_name.split(" ")[0] ?? full_name,
  last_name: full_name.split(" ")[1] ?? "",
  full_name,
  position: "Сварщик",
  company_id: "c1",
  status
});

const item = (id: string, name: string) => ({ id, name, code: id, category: "head" });

beforeEach(() => {
  getPpeOverviewMock.mockReset();
  createPpeIssueMock.mockReset();
  listLevelsMock.mockReset();
  getPpeOverviewMock.mockResolvedValue({
    persons: [person("p1", "Иван Иванов"), person("p2", "Пётр Петров", "dismissed")],
    items: [item("i1", "Каска"), item("i2", "Перчатки")],
    issues: [],
    expiring: []
  });
  listLevelsMock.mockResolvedValue([{ item_id: "i1", item_name: "Каска", total_quantity: 5, batch_count: 1 }]);
  createPpeIssueMock.mockResolvedValue({ id: "x", person_id: "p1", item_id: "i1", quantity: 1, status: "issued" });
});

describe("useMobileIssue", () => {
  it("loads data, exposes only active persons, is stock-aware when listLevels resolves", async () => {
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.activePersons.map((p) => p.id)).toEqual(["p1"]);
    expect(result.current.stockAware).toBe(true);
    expect(result.current.onHandFor("i1")).toBe(5);
    expect(result.current.onHandFor("i2")).toBe(0);
  });

  it("degrades silently when listLevels rejects (warehouse flag off)", async () => {
    listLevelsMock.mockRejectedValue({ message: "404" });
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.stockAware).toBe(false);
    expect(result.current.onHandFor("i1")).toBeNull();
  });

  it("selects worker, merges duplicate cart items, clamps qty, removes", async () => {
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.selectWorker(result.current.activePersons[0]));
    expect(result.current.step).toBe("items");
    act(() => result.current.addItem({ id: "i1", name: "Каска", code: "i1", category: "head" }));
    act(() => result.current.addItem({ id: "i1", name: "Каска", code: "i1", category: "head" }));
    expect(result.current.cart).toHaveLength(1);
    expect(result.current.cart[0].quantity).toBe(2);
    act(() => result.current.setQty("i1", 0));
    expect(result.current.cart[0].quantity).toBe(1);
    act(() => result.current.removeItem("i1"));
    expect(result.current.cart).toHaveLength(0);
  });

  it("issues all lines, clears cart, calls createPpeIssue per line with worker id", async () => {
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.selectWorker(result.current.activePersons[0]));
    act(() => result.current.addItem({ id: "i1", name: "Каска", code: "i1", category: "head" }));
    act(() => result.current.addItem({ id: "i2", name: "Перчатки", code: "i2", category: "hand" }));
    await act(async () => { await result.current.issueAll(); });
    expect(createPpeIssueMock).toHaveBeenCalledTimes(2);
    expect(createPpeIssueMock).toHaveBeenCalledWith({ person_id: "p1", item_id: "i1", quantity: 1 });
    expect(result.current.results?.every((r) => r.status === "ok")).toBe(true);
    expect(result.current.allIssued).toBe(true);
    expect(result.current.cart).toHaveLength(0);
  });

  it("on partial failure keeps only failed lines; retry re-sends only those", async () => {
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.selectWorker(result.current.activePersons[0]));
    act(() => result.current.addItem({ id: "i1", name: "Каска", code: "i1", category: "head" }));
    act(() => result.current.addItem({ id: "i2", name: "Перчатки", code: "i2", category: "hand" }));
    createPpeIssueMock
      .mockResolvedValueOnce({ id: "a" })
      .mockRejectedValueOnce({ message: "Недостаточно остатка" });
    await act(async () => { await result.current.issueAll(); });
    expect(result.current.cart).toEqual([expect.objectContaining({ item_id: "i2" })]);
    expect(result.current.results?.find((r) => r.item_id === "i2")?.error).toBe("Недостаточно остатка");
    expect(result.current.allIssued).toBe(false);
    createPpeIssueMock.mockResolvedValue({ id: "b" });
    await act(async () => { await result.current.issueAll(); });
    expect(createPpeIssueMock).toHaveBeenCalledTimes(3); // 2 first attempt + 1 retry
    expect(result.current.cart).toHaveLength(0);
  });

  it("guards against synchronous double submit", async () => {
    const { result } = renderHook(() => useMobileIssue());
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.selectWorker(result.current.activePersons[0]));
    act(() => result.current.addItem({ id: "i1", name: "Каска", code: "i1", category: "head" }));
    let release!: () => void;
    createPpeIssueMock.mockReturnValue(new Promise((res) => { release = () => res({ id: "z" }); }));
    await act(async () => {
      const first = result.current.issueAll();
      const second = result.current.issueAll(); // must be a no-op (in-flight)
      release();
      await Promise.all([first, second]);
    });
    expect(createPpeIssueMock).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm --prefix frontend exec vitest run src/__tests__/useMobileIssue.test.tsx`
Expected: FAIL — cannot resolve `@/pages/ppe/mobile-issue/useMobileIssue`.

- [ ] **Step 4: Implement the hook**

`frontend/src/pages/ppe/mobile-issue/useMobileIssue.ts`:

```ts
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { opsApi, type PpeItemDto } from "@/api/ops";
import { warehouseApi } from "@/api/warehouse";
import type { ApiError } from "@/types/dto/common";
import type { PersonDto } from "@/types/dto/persons";

import type { CartLine, IssueResultLine, MobileIssueStep } from "./types";

export function useMobileIssue() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [persons, setPersons] = useState<PersonDto[]>([]);
  const [items, setItems] = useState<PpeItemDto[]>([]);
  const [stockAware, setStockAware] = useState(false);
  const [onHand, setOnHand] = useState<Map<string, number>>(new Map());

  const [step, setStep] = useState<MobileIssueStep>("worker");
  const [worker, setWorker] = useState<PersonDto | null>(null);
  const [cart, setCart] = useState<CartLine[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState<IssueResultLine[] | null>(null);
  const submittingRef = useRef(false); // synchronous double-tap guard

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const snapshot = await opsApi.getPpeOverview();
      setPersons(snapshot.persons);
      setItems(snapshot.items);
      // /ppe/stock/levels is gated by the warehouse feature flag; a 404/403 just
      // means "no stock tracking" — degrade silently, issuance still works.
      try {
        const levels = await warehouseApi.listLevels();
        setOnHand(new Map(levels.map((lvl) => [lvl.item_id, lvl.total_quantity])));
        setStockAware(true);
      } catch {
        setOnHand(new Map());
        setStockAware(false);
      }
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить данные выдачи СИЗ" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const activePersons = useMemo(() => persons.filter((p) => p.status === "active"), [persons]);

  const onHandFor = useCallback(
    (itemId: string): number | null => (stockAware ? onHand.get(itemId) ?? 0 : null),
    [stockAware, onHand]
  );

  const selectWorker = useCallback((person: PersonDto) => {
    setWorker(person);
    setStep("items");
  }, []);

  const reset = useCallback(() => {
    setWorker(null);
    setCart([]);
    setResults(null);
    setStep("worker");
  }, []);

  const addItem = useCallback(
    (item: PpeItemDto) => {
      setResults(null);
      setCart((prev) => {
        const existing = prev.find((line) => line.item_id === item.id);
        if (existing) {
          return prev.map((line) =>
            line.item_id === item.id ? { ...line, quantity: line.quantity + 1 } : line
          );
        }
        return [...prev, { item_id: item.id, item_name: item.name, quantity: 1, on_hand: onHandFor(item.id) }];
      });
    },
    [onHandFor]
  );

  const setQty = useCallback((itemId: string, quantity: number) => {
    setResults(null);
    setCart((prev) =>
      prev.map((line) =>
        line.item_id === itemId ? { ...line, quantity: Math.max(1, Math.floor(quantity) || 1) } : line
      )
    );
  }, []);

  const removeItem = useCallback((itemId: string) => {
    setResults(null);
    setCart((prev) => prev.filter((line) => line.item_id !== itemId));
  }, []);

  const issueAll = useCallback(async () => {
    if (submittingRef.current || !worker || cart.length === 0) return;
    submittingRef.current = true;
    setSubmitting(true);
    try {
      const lineResults: IssueResultLine[] = [];
      for (const line of cart) {
        try {
          await opsApi.createPpeIssue({ person_id: worker.id, item_id: line.item_id, quantity: line.quantity });
          lineResults.push({ item_id: line.item_id, item_name: line.item_name, quantity: line.quantity, status: "ok" });
        } catch (err) {
          const apiErr = err as ApiError;
          lineResults.push({
            item_id: line.item_id,
            item_name: line.item_name,
            quantity: line.quantity,
            status: "error",
            error: apiErr?.message || "Не удалось выдать позицию"
          });
        }
      }
      // Drop successfully-issued lines so a retry re-sends only failed ones
      // (prevents double-issue without server-side idempotency).
      const okIds = new Set(lineResults.filter((r) => r.status === "ok").map((r) => r.item_id));
      setCart((prev) => prev.filter((line) => !okIds.has(line.item_id)));
      setResults(lineResults);
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }, [worker, cart]);

  const allIssued = useMemo(
    () => results !== null && results.length > 0 && results.every((r) => r.status === "ok"),
    [results]
  );

  return {
    loading,
    error,
    reload: load,
    step,
    setStep,
    persons,
    activePersons,
    items,
    stockAware,
    onHandFor,
    worker,
    selectWorker,
    reset,
    cart,
    addItem,
    setQty,
    removeItem,
    submitting,
    results,
    issueAll,
    allIssued
  };
}

export type UseMobileIssue = ReturnType<typeof useMobileIssue>;
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `npm --prefix frontend exec vitest run src/__tests__/useMobileIssue.test.tsx`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ppe/mobile-issue/types.ts frontend/src/pages/ppe/mobile-issue/useMobileIssue.ts frontend/src/__tests__/useMobileIssue.test.tsx
git commit -m "feat(p10-06): useMobileIssue hook — cart + issueAll (online-first)"
```

---

## Task 2: Page shell + route + worker step

**Files:**
- Create: `frontend/src/pages/ppe/MobileIssuePage.tsx`
- Modify: `frontend/src/router/pageRegistry.tsx` (add lazy export after line 15, the `PpePage` export)
- Modify: `frontend/src/router/routeGroups.tsx` (barrel import + route group near the `/ppe` group at line ~145)
- Test: `frontend/src/__tests__/MobileIssuePage.test.tsx`

- [ ] **Step 1: Write the failing page test (worker step)**

`frontend/src/__tests__/MobileIssuePage.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MobileIssuePage from "@/pages/ppe/MobileIssuePage";

const getPpeOverviewMock = vi.fn();
const createPpeIssueMock = vi.fn();
const listLevelsMock = vi.fn();

vi.mock("@/api/ops", () => ({
  opsApi: {
    getPpeOverview: (...a: unknown[]) => getPpeOverviewMock(...a),
    createPpeIssue: (...a: unknown[]) => createPpeIssueMock(...a)
  }
}));
vi.mock("@/api/warehouse", () => ({
  warehouseApi: { listLevels: (...a: unknown[]) => listLevelsMock(...a) }
}));

const person = (id: string, full_name: string, status = "active") => ({
  id, created_at: "2024-01-01", updated_at: "2024-01-02",
  first_name: full_name, last_name: "", full_name, position: "Сварщик", company_id: "c1", status
});
const item = (id: string, name: string) => ({ id, name, code: id, category: "head" });

const renderPage = () =>
  render(
    <MemoryRouter>
      <MobileIssuePage />
    </MemoryRouter>
  );

beforeEach(() => {
  getPpeOverviewMock.mockReset();
  createPpeIssueMock.mockReset();
  listLevelsMock.mockReset();
  getPpeOverviewMock.mockResolvedValue({
    persons: [person("p1", "Иван Иванов"), person("p2", "Уволенный Работник", "dismissed")],
    items: [item("i1", "Каска"), item("i2", "Перчатки")],
    issues: [],
    expiring: []
  });
  listLevelsMock.mockResolvedValue([{ item_id: "i1", item_name: "Каска", total_quantity: 5, batch_count: 1 }]);
  createPpeIssueMock.mockResolvedValue({ id: "x" });
});

describe("MobileIssuePage — worker step", () => {
  it("renders the page and lists only active workers, selecting one advances to items", async () => {
    renderPage();
    expect(await screen.findByText("Мобильная выдача СИЗ")).toBeInTheDocument();
    expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
    expect(screen.queryByText("Уволенный Работник")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Иван Иванов"));

    await waitFor(() => expect(screen.getByLabelText("Поиск СИЗ")).toBeInTheDocument());
  });

  it("filters workers by query", async () => {
    getPpeOverviewMock.mockResolvedValue({
      persons: [person("p1", "Иван Иванов"), person("p3", "Сидор Сидоров")],
      items: [], issues: [], expiring: []
    });
    renderPage();
    await screen.findByText("Иван Иванов");
    fireEvent.change(screen.getByLabelText("Поиск сотрудника"), { target: { value: "сидор" } });
    expect(screen.getByText("Сидор Сидоров")).toBeInTheDocument();
    expect(screen.queryByText("Иван Иванов")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix frontend exec vitest run src/__tests__/MobileIssuePage.test.tsx`
Expected: FAIL — cannot resolve `@/pages/ppe/MobileIssuePage`.

- [ ] **Step 3: Create the page (full file — items/review steps included so later tasks only add tests)**

`frontend/src/pages/ppe/MobileIssuePage.tsx`:

```tsx
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { useMobileIssue } from "./mobile-issue/useMobileIssue";

const MobileIssuePage = () => {
  const navigate = useNavigate();
  const issue = useMobileIssue();
  const [workerQuery, setWorkerQuery] = useState("");
  const [itemQuery, setItemQuery] = useState("");

  const workerResults = useMemo(() => {
    const q = workerQuery.trim().toLowerCase();
    const base = issue.activePersons;
    if (!q) return base.slice(0, 20);
    return base.filter((p) => `${p.full_name} ${p.position ?? ""}`.toLowerCase().includes(q)).slice(0, 20);
  }, [issue.activePersons, workerQuery]);

  const itemResults = useMemo(() => {
    const q = itemQuery.trim().toLowerCase();
    if (!q) return issue.items.slice(0, 30);
    return issue.items.filter((it) => `${it.name} ${it.code}`.toLowerCase().includes(q)).slice(0, 30);
  }, [issue.items, itemQuery]);

  const cartCount = issue.cart.reduce((sum, line) => sum + line.quantity, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumb
          items={[
            { label: "Главная", to: "/dashboard" },
            { label: "СИЗ и склады", to: "/ppe" },
            { label: "Мобильная выдача" }
          ]}
        />
        <Button variant="outline" onClick={() => navigate("/ppe")}>
          К карточкам СИЗ
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Мобильная выдача СИЗ</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ErrorState error={issue.error ?? undefined} onRetry={issue.reload} />
          {issue.loading ? <LoadingScreen label="Загрузка данных выдачи" /> : null}

          {!issue.loading && !issue.error ? (
            <>
              {issue.worker ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/40 p-3">
                  <div>
                    <div className="font-medium">{issue.worker.full_name}</div>
                    <div className="text-sm text-muted-foreground">{issue.worker.position ?? "—"}</div>
                  </div>
                  <Button variant="ghost" onClick={issue.reset}>
                    Сменить сотрудника
                  </Button>
                </div>
              ) : null}

              {issue.step === "worker" ? (
                <section className="space-y-3" aria-label="Выбор сотрудника">
                  <input
                    type="search"
                    className="h-11 w-full rounded-md border px-3 text-base"
                    placeholder="Поиск сотрудника по ФИО или должности"
                    aria-label="Поиск сотрудника"
                    value={workerQuery}
                    onChange={(e) => setWorkerQuery(e.target.value)}
                  />
                  {workerResults.length === 0 ? (
                    <EmptyState title="Сотрудники не найдены" description="Уточните запрос или проверьте справочник сотрудников." />
                  ) : (
                    <ul className="space-y-2">
                      {workerResults.map((person) => (
                        <li key={person.id}>
                          <button
                            type="button"
                            className="flex w-full items-center justify-between rounded-md border p-3 text-left hover:bg-accent"
                            onClick={() => issue.selectWorker(person)}
                          >
                            <span className="font-medium">{person.full_name}</span>
                            <span className="text-sm text-muted-foreground">{person.position ?? "—"}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ) : null}

              {issue.step === "items" ? (
                <section className="space-y-4" aria-label="Выбор СИЗ">
                  <input
                    type="search"
                    className="h-11 w-full rounded-md border px-3 text-base"
                    placeholder="Поиск СИЗ по названию или коду"
                    aria-label="Поиск СИЗ"
                    value={itemQuery}
                    onChange={(e) => setItemQuery(e.target.value)}
                  />
                  <ul className="space-y-2">
                    {itemResults.map((item) => {
                      const onHand = issue.onHandFor(item.id);
                      return (
                        <li key={item.id} className="flex items-center justify-between rounded-md border p-3">
                          <div>
                            <div className="font-medium">{item.name}</div>
                            {issue.stockAware ? (
                              <div className="text-sm text-muted-foreground">На складе: {onHand}</div>
                            ) : null}
                          </div>
                          <Button size="sm" onClick={() => issue.addItem(item)}>
                            + Добавить
                          </Button>
                        </li>
                      );
                    })}
                  </ul>

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Корзина ({cartCount})</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {issue.cart.length === 0 ? (
                        <p className="text-sm text-muted-foreground">Добавьте позиции СИЗ для выдачи.</p>
                      ) : (
                        <ul className="space-y-2">
                          {issue.cart.map((line) => {
                            const short = line.on_hand !== null && line.quantity > line.on_hand;
                            return (
                              <li key={line.item_id} className="flex items-center justify-between gap-2 rounded-md border p-2">
                                <div className="min-w-0">
                                  <div className="truncate font-medium">{line.item_name}</div>
                                  {short ? (
                                    <div className="text-sm text-destructive">Больше, чем на складе ({line.on_hand})</div>
                                  ) : null}
                                </div>
                                <div className="flex items-center gap-2">
                                  <Button size="sm" variant="outline" aria-label={`Уменьшить ${line.item_name}`} onClick={() => issue.setQty(line.item_id, line.quantity - 1)}>
                                    −
                                  </Button>
                                  <span className="w-8 text-center" aria-label={`Количество ${line.item_name}`}>
                                    {line.quantity}
                                  </span>
                                  <Button size="sm" variant="outline" aria-label={`Увеличить ${line.item_name}`} onClick={() => issue.setQty(line.item_id, line.quantity + 1)}>
                                    +
                                  </Button>
                                  <Button size="sm" variant="ghost" onClick={() => issue.removeItem(line.item_id)}>
                                    Удалить
                                  </Button>
                                </div>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </CardContent>
                  </Card>

                  <div className="flex justify-between gap-2">
                    <Button variant="ghost" onClick={issue.reset}>
                      Отмена
                    </Button>
                    <Button disabled={issue.cart.length === 0} onClick={() => issue.setStep("review")}>
                      К обзору ({cartCount})
                    </Button>
                  </div>
                </section>
              ) : null}

              {issue.step === "review" ? (
                <section className="space-y-4" aria-label="Обзор и выдача">
                  {issue.allIssued ? (
                    <div className="space-y-3">
                      <div className="rounded-md border border-green-600/40 bg-green-50 p-3 text-green-800">
                        Выдано позиций: {issue.results?.length ?? 0}. Работник: {issue.worker?.full_name}
                      </div>
                      <Button onClick={issue.reset}>Новая выдача</Button>
                    </div>
                  ) : (
                    <>
                      <ul className="space-y-2">
                        {issue.cart.map((line) => (
                          <li key={line.item_id} className="flex items-center justify-between rounded-md border p-3">
                            <span className="font-medium">{line.item_name}</span>
                            <span>× {line.quantity}</span>
                          </li>
                        ))}
                      </ul>
                      {issue.results ? (
                        <ul className="space-y-1" aria-label="Результат выдачи">
                          {issue.results.map((r) => (
                            <li key={r.item_id} className={r.status === "ok" ? "text-green-700" : "text-destructive"}>
                              {r.status === "ok" ? "✓" : "✗"} {r.item_name} × {r.quantity}
                              {r.status === "error" && r.error ? ` — ${r.error}` : ""}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <div className="flex justify-between gap-2">
                        <Button variant="ghost" onClick={() => issue.setStep("items")}>
                          Назад
                        </Button>
                        <Button disabled={issue.submitting || issue.cart.length === 0} onClick={() => void issue.issueAll()}>
                          {issue.submitting ? "Выдача…" : `Выдать всё (${cartCount})`}
                        </Button>
                      </div>
                    </>
                  )}
                </section>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};

export default MobileIssuePage;
```

- [ ] **Step 4: Register the lazy component**

In `frontend/src/router/pageRegistry.tsx`, add directly after the `PpePage` export (line 15):

```ts
export const MobileIssuePage = lazy(() => import("@/pages/ppe/MobileIssuePage"));
```

- [ ] **Step 5: Register the route**

In `frontend/src/router/routeGroups.tsx`:
1. Add `MobileIssuePage,` to the barrel import block (alphabetically near `MedicalPage`/`NotificationsPage`, or right after `PpePage,` at line 54 — any spot in the `{ ... } from "@/router/pageRegistry"`-style import is fine as long as it compiles).
2. Add a route group immediately after the `/ppe` group (line 145):

```tsx
{ permission: PERMISSIONS.PPE_ISSUE, routes: [<Route key="/ppe/issue" path="/ppe/issue" element={<MobileIssuePage />} />] },
```

- [ ] **Step 6: Run the page test to verify it passes**

Run: `npm --prefix frontend exec vitest run src/__tests__/MobileIssuePage.test.tsx`
Expected: PASS (2 tests — worker step).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ppe/MobileIssuePage.tsx frontend/src/router/pageRegistry.tsx frontend/src/router/routeGroups.tsx frontend/src/__tests__/MobileIssuePage.test.tsx
git commit -m "feat(p10-06): mobile issuance page shell + /ppe/issue route + worker step"
```

---

## Task 3: Items step + cart tests (stock-aware and degraded)

**Files:**
- Test: `frontend/src/__tests__/MobileIssuePage.test.tsx` (append a `describe` block)

The items/cart UI already exists (built in Task 2). This task adds the behavioral tests.

- [ ] **Step 1: Append the failing tests**

Append to `frontend/src/__tests__/MobileIssuePage.test.tsx`:

```tsx
describe("MobileIssuePage — items & cart", () => {
  const gotoItems = async () => {
    renderPage();
    fireEvent.click(await screen.findByText("Иван Иванов"));
    await screen.findByLabelText("Поиск СИЗ");
  };

  it("adds items to the cart and merges duplicates", async () => {
    await gotoItems();
    const addButtons = screen.getAllByRole("button", { name: "+ Добавить" });
    fireEvent.click(addButtons[0]); // Каска
    expect(await screen.findByText("Корзина (1)")).toBeInTheDocument();
    fireEvent.click(addButtons[0]); // Каска again → merge → qty 2
    expect(await screen.findByText("Корзина (2)")).toBeInTheDocument();
    expect(screen.getByLabelText("Количество Каска")).toHaveTextContent("2");
  });

  it("shows on-hand badge when stock-aware", async () => {
    await gotoItems();
    expect(await screen.findByText("На складе: 5")).toBeInTheDocument();
  });

  it("hides on-hand badge when stock levels unavailable (degraded)", async () => {
    listLevelsMock.mockRejectedValue({ message: "404" });
    await gotoItems();
    await screen.findByText("Каска");
    expect(screen.queryByText(/На складе:/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify (should PASS immediately — UI exists from Task 2)**

Run: `npm --prefix frontend exec vitest run src/__tests__/MobileIssuePage.test.tsx`
Expected: PASS (5 tests total). If the merge/badge assertions fail, fix the page (Task 2 code), not the test.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/MobileIssuePage.test.tsx
git commit -m "test(p10-06): mobile issuance items/cart — merge + stock-aware/degraded"
```

---

## Task 4: Review step — issue-all success, partial failure, double-tap

**Files:**
- Test: `frontend/src/__tests__/MobileIssuePage.test.tsx` (append a `describe` block)

- [ ] **Step 1: Append the failing tests**

```tsx
describe("MobileIssuePage — review & issue", () => {
  const gotoReviewWithKaska = async () => {
    renderPage();
    fireEvent.click(await screen.findByText("Иван Иванов"));
    await screen.findByLabelText("Поиск СИЗ");
    fireEvent.click(screen.getAllByRole("button", { name: "+ Добавить" })[0]); // Каска
    fireEvent.click(await screen.findByRole("button", { name: /К обзору/ }));
    await screen.findByRole("button", { name: /Выдать всё/ });
  };

  it("issues the whole cart and shows a success panel", async () => {
    await gotoReviewWithKaska();
    fireEvent.click(screen.getByRole("button", { name: /Выдать всё/ }));
    expect(await screen.findByText(/Выдано позиций: 1/)).toBeInTheDocument();
    expect(createPpeIssueMock).toHaveBeenCalledWith({ person_id: "p1", item_id: "i1", quantity: 1 });
  });

  it("on failure shows the error and keeps the failed line for retry", async () => {
    createPpeIssueMock.mockRejectedValueOnce({ message: "Недостаточно остатка" });
    await gotoReviewWithKaska();
    fireEvent.click(screen.getByRole("button", { name: /Выдать всё/ }));
    expect(await screen.findByText(/Недостаточно остатка/)).toBeInTheDocument();
    // failed line still issuable → button present, not a success panel
    expect(screen.getByRole("button", { name: /Выдать всё/ })).toBeInTheDocument();
    expect(screen.queryByText(/Выдано позиций/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify (should PASS immediately — UI exists from Task 2)**

Run: `npm --prefix frontend exec vitest run src/__tests__/MobileIssuePage.test.tsx`
Expected: PASS (7 tests total).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/MobileIssuePage.test.tsx
git commit -m "test(p10-06): mobile issuance review — success + partial-failure retry"
```

---

## Task 5: Entry-point button on PpePage

**Files:**
- Modify: `frontend/src/pages/ppe/PpePage.tsx`
- Test: `frontend/src/__tests__/PpePage.test.tsx` (append one test)

- [ ] **Step 1: Append the failing test**

Append inside the existing `describe("PpePage", ...)` in `frontend/src/__tests__/PpePage.test.tsx`:

```tsx
  it("shows a link to mobile issuance for users who can issue", async () => {
    useAuthStore.setState({
      user: { ...baseUser, permissions: [PERMISSIONS.PPE_VIEW, PERMISSIONS.PPE_ISSUE] },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });

    render(
      <MemoryRouter>
        <PpePage />
      </MemoryRouter>
    );

    expect(await screen.findByRole("button", { name: /мобильная выдача/i })).toBeEnabled();
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix frontend exec vitest run src/__tests__/PpePage.test.tsx`
Expected: FAIL — no "Мобильная выдача" button.

- [ ] **Step 3: Add the button to PpePage**

In `frontend/src/pages/ppe/PpePage.tsx`:
1. Change the import on line 2 to also bring in `useNavigate`:

```ts
import { useNavigate, useSearchParams } from "react-router-dom";
```

2. Inside the component, after `const [searchParams, setSearchParams] = useSearchParams();` (line 20), add:

```ts
  const navigate = useNavigate();
```

3. In the header actions `<div className="flex gap-2">` (line 117), add — right before the `<Can ...>` quick-issue block (line 136) — a gated navigation button:

```tsx
          <Can permission={PERMISSIONS.PPE_ISSUE}>
            <Button variant="outline" onClick={() => navigate("/ppe/issue")}>
              Мобильная выдача
            </Button>
          </Can>
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm --prefix frontend exec vitest run src/__tests__/PpePage.test.tsx`
Expected: PASS (existing tests + the new one).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ppe/PpePage.tsx frontend/src/__tests__/PpePage.test.tsx
git commit -m "feat(p10-06): link to mobile issuance from the PPE page"
```

---

## Task 6: Docs + full gates

**Files:**
- Modify: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` (P10-06 row)
- Modify: `CHANGELOG.md`
- Modify: `AI_IMPLEMENTATION_REPORT.md` (prepend a handoff block at the top)

- [ ] **Step 1: Run the full frontend gates**

Run all three, expect exit 0:

```
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

Expected: `tsc` 0 errors; vitest all suites green (incl. `useMobileIssue`, `MobileIssuePage`, `PpePage`, `WarehousePage`); `vite build` succeeds. If anything fails, fix the source and re-run — do not proceed until all three are green.

- [ ] **Step 2: Update the roadmap P10-06 row**

In `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, find the `| **P10-06** | СИЗ склад (полный) |` row. In its prose add a "Мобильная выдача" clause, and in the trailing **Остаётся:** change `бюджет безопасности, мобильная выдача` → `бюджет безопасности`. Example edit to the `**Остаётся:**` fragment:

```
**Остаётся:** бюджет безопасности (мобильная выдача — влита: online-first корзинный экран `/ppe/issue` поверх `POST /ppe/issues`, поиск сотрудника + корзина + выдать всё, stock-aware с тихой деградацией при выключенном флаге warehouse)
```

Also update the **Summary** line lower in the same section: in the `P10-06 СИЗ-склад (поставщики/бюджет безопасности/мобильная выдача)` enumeration, drop `мобильная выдача`.

- [ ] **Step 3: Add a CHANGELOG entry**

Prepend under the top/Unreleased section of `CHANGELOG.md` (match the existing bullet style):

```markdown
### P10-06 СИЗ-склад — мобильная выдача (online-first)
- Новый touch-first экран `/ppe/issue` (право `ppe.issue`): поиск сотрудника → корзина позиций СИЗ → выдать всё. Поверх готового `POST /ppe/issues` (FIFO-списание). Stock-aware бейджи остатка при включённом флаге `warehouse`, тихая деградация при выключенном. Частичный отказ оставляет только неудачные строки для повтора; guard от двойного тапа. Чисто фронтовый срез (без миграций/новых эндпоинтов).
```

- [ ] **Step 4: Prepend a handoff block to `AI_IMPLEMENTATION_REPORT.md`**

Insert at the very top (after `# AI Implementation Report`), matching the existing block format. Include: date 2026-07-05, decisions (online-first / cart / typeahead / confirm-only), the frontend-only nature (no backend/migration/OpenAPI/PG), files touched, verification (tsc/vitest/build results), deferred follow-ups (offline queue + server idempotency, QR scan, signature, 766н norm-driven, per-line batch), and the "Next точный шаг" (бюджет безопасности; or P10-03 медосмотры / P10-07 report-builder). Note the branch is NOT merged — merge/PR is the user's decision.

- [ ] **Step 5: Commit**

```bash
git add docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md CHANGELOG.md AI_IMPLEMENTATION_REPORT.md docs/superpowers/plans/2026-07-05-p10-06-ppe-mobile-issuance.md
git commit -m "docs(p10-06): roadmap + changelog + handoff + plan for mobile issuance"
```

---

## Self-Review

**1. Spec coverage:**
- Online-first, cart/kit flow → Tasks 1–4. ✅
- Worker typeahead, active-only → Task 1 (`activePersons`) + Task 2 tests. ✅
- Confirm-only (no signature) → review step, no signature UI. ✅
- Stock-aware + silent degradation → hook `stockAware`/`onHandFor` + Task 3 tests. ✅
- Partial-failure retry (drop ok lines) + double-tap guard → hook `issueAll` + `submittingRef`, Task 1 + Task 4 tests. ✅
- Route `/ppe/issue` gated `PPE_ISSUE` + entry point on PpePage → Tasks 2 & 5. ✅
- Honest-stock invariant untouched (rides `createPpeIssue`) → no `stock.py`/model changes. ✅
- No backend/migration/OpenAPI/PG → only frontend files touched; Task 6 runs frontend gates only. ✅
- Deferred items (offline, QR, signature, norms, per-line batch) → documented in Task 6 handoff; not implemented. ✅

**2. Placeholder scan:** No TBD/TODO; every code step has complete code; commands have expected output. Task 6 steps 2–4 are doc edits described with concrete target strings (acceptable — they are prose edits, not code).

**3. Type consistency:** `CartLine`/`IssueResultLine`/`MobileIssueStep` defined in Task 1 `types.ts` and used identically by the hook and page. Hook return keys (`activePersons`, `onHandFor`, `selectWorker`, `addItem`, `setQty`, `removeItem`, `issueAll`, `allIssued`, `reset`, `setStep`, `reload`, `stockAware`, `submitting`, `results`, `worker`, `cart`, `items`, `loading`, `error`) match exactly what `MobileIssuePage.tsx` consumes. `opsApi.createPpeIssue` payload `{ person_id, item_id, quantity }` matches `CreatePpeIssuePayload`. `warehouseApi.listLevels()` → `StockLevelDto` (`item_id`/`total_quantity`) matches the hook’s map. `PERMISSIONS.PPE_ISSUE` is the real constant.

## Anti-gotchas (from prior handoffs)

- **Frontend-only:** never create routes/schemas/models/migrations on the backend; never re-snapshot OpenAPI; never run the PG16 gate or ruff/black. Gates are `tsc`/`vitest`/`build` only.
- **`createPpeIssue` has no `batch_id`** in the frontend `CreatePpeIssuePayload` — do not invent one (auto-FIFO). Per-line batch pick is a follow-up.
- **`listLevels()` must be wrapped in try/catch** — it 404s when the `warehouse` flag is off; silent degrade or the whole page dies on flag-off tenants.
- **Double-tap guard uses a `useRef`**, not the `submitting` state — React state updates are async, so a synchronous second `issueAll()` would slip past a state-based check.
- **Partial-failure:** drop only `ok` lines before a retry, or the retry re-issues succeeded lines (double-issue).
- **Worktree has no `node_modules`** — run `npm ci --prefer-offline` in `frontend/` first if needed; run vitest/tsc/build via the PowerShell tool.
- **Match house style:** single-file page, hardcoded Russian strings, no i18n (this layer doesn’t use it).
```
