# W2 Command Center UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a "Командный центр" page that surfaces the operational alerts aggregator (`GET /api/v1/operational/dashboard`) as severity-sorted category widgets, with polling refresh.

**Architecture:** Mirror the already-shipped Health UI contour layer-for-layer: thin `api/` client + DTO types → Zustand+immer `stores/` loader → pure presentational `components/` panel (tested without network) → `pages/` glue that owns the poll timer → `router/` registration (pageRegistry → routeGroups guard → navigationConfig). Backend is unchanged.

**Tech Stack:** React + TypeScript, Zustand (immer middleware), react-router-dom, Tailwind, lucide-react, Vitest + Testing Library. Russian UI.

**Spec:** [docs/superpowers/specs/2026-06-15-w2-command-center-ui-design.md](../specs/2026-06-15-w2-command-center-ui-design.md)

**Branch:** `feat/w2-command-center-ui` (spec already committed there).

**Verification commands (run from repo root):**
- Typecheck: `npm --prefix frontend run typecheck`
- Lint: `npm --prefix frontend run lint`
- Single test file: `cd frontend; npx vitest run src/__tests__/CommandCenterPanel.test.tsx`

---

## File Structure

| File | Responsibility |
|---|---|
| **new** `frontend/src/api/operationalDashboard.ts` | DTO types (mirror backend schema) + thin `getDashboard()` client |
| **new** `frontend/src/stores/operationalDashboard.ts` | Zustand loader: `{ data, loading, error, fetchDashboard, reset }` |
| **new** `frontend/src/components/operational/CommandCenterPanel.tsx` | Pure presentation: header/status, severity chips, category cards, empty/error/loading |
| **new** `frontend/src/pages/operational/CommandCenterPage.tsx` | Store↔panel glue; owns 30s poll timer + visibilitychange refetch |
| **new** `frontend/src/__tests__/CommandCenterPanel.test.tsx` | Unit tests for the pure panel |
| **edit** `frontend/src/router/pageRegistry.tsx` | Lazy export `CommandCenterPage` |
| **edit** `frontend/src/router/routeGroups.tsx` | Route `/command-center` under `DASHBOARD_VIEW` group |
| **edit** `frontend/src/router/navigationConfig.ts` | Nav item "Командный центр" in "Документооборот" group |

---

## Task 1: API client + DTO types

**Files:**
- Create: `frontend/src/api/operationalDashboard.ts`

- [ ] **Step 1: Create the API module with types**

```ts
import { apiClient } from "@/api/client";

export type AlertSeverity = "critical" | "high" | "medium" | "low";

export type AlertCategory =
  | "overdue"
  | "blocked_approval"
  | "integration_error"
  | "high_risk"
  | "health_warning"
  | "unassigned_task"
  | "data_quality";

/** One alert bucket from GET /api/v1/operational/dashboard (backend: AlertItem). */
export type AlertItem = {
  id: string;
  category: AlertCategory;
  severity: AlertSeverity;
  title: string;
  description?: string | null;
  count: number;
  affected_entity_type?: string | null;
  affected_entity_id?: string | null;
  action_url?: string | null;
  created_at: string;
  expires_at?: string | null;
};

export type OperationalDashboardStatus = "ok" | "warning" | "critical";

/** Backend: OperationalDashboardResponse. */
export type OperationalDashboardDto = {
  tenant_id: string;
  status: OperationalDashboardStatus;
  alerts: AlertItem[];
  alert_count: Partial<Record<AlertSeverity, number>>;
  health_status?: string | null;
  timestamp: string;
};

export const operationalDashboardApi = {
  /**
   * Operational alerts aggregator. X-Tenant-Id is injected by apiClient
   * (same mechanism the health contour relies on).
   */
  getDashboard: async (): Promise<OperationalDashboardDto> => {
    const response = await apiClient.get<OperationalDashboardDto>("/operational/dashboard");
    return response.data;
  }
};
```

- [ ] **Step 2: Verify it typechecks**

Run: `npm --prefix frontend run typecheck`
Expected: PASS (no errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/operationalDashboard.ts
git commit -m "feat(w2): operational dashboard api client + DTO types"
```

---

## Task 2: CommandCenterPanel (TDD — test first)

**Files:**
- Create: `frontend/src/__tests__/CommandCenterPanel.test.tsx`
- Create: `frontend/src/components/operational/CommandCenterPanel.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/CommandCenterPanel.test.tsx`:

```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { OperationalDashboardDto } from "@/api/operationalDashboard";
import { CommandCenterPanel } from "@/components/operational/CommandCenterPanel";

const renderPanel = (props: Parameters<typeof CommandCenterPanel>[0]) =>
  render(
    <MemoryRouter>
      <CommandCenterPanel {...props} />
    </MemoryRouter>
  );

const data: OperationalDashboardDto = {
  tenant_id: "tenant-1",
  status: "critical",
  timestamp: "2026-06-15T00:00:00Z",
  health_status: "ok",
  alert_count: { critical: 1, high: 2 },
  alerts: [
    {
      id: "a1",
      category: "high_risk",
      severity: "critical",
      title: "Критический риск на объекте",
      description: "PxS высокий",
      count: 3,
      action_url: "/risk",
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-06-15T00:00:00Z",
      expires_at: null
    },
    {
      id: "a2",
      category: "overdue",
      severity: "high",
      title: "Просроченные обучения",
      description: null,
      count: 5,
      action_url: "/training",
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-06-15T00:00:00Z",
      expires_at: null
    },
    {
      id: "a3",
      category: "integration_error",
      severity: "high",
      title: "Сбой интеграции 1С",
      description: null,
      count: 1,
      action_url: null,
      affected_entity_type: null,
      affected_entity_id: null,
      created_at: "2026-06-15T00:00:00Z",
      expires_at: null
    }
  ]
};

describe("CommandCenterPanel", () => {
  it("renders a card per non-empty category with RU labels and overall status", () => {
    renderPanel({ data });
    expect(screen.getByText("Высокий риск")).toBeInTheDocument();
    expect(screen.getByText("Просроченные")).toBeInTheDocument();
    expect(screen.getByText("Ошибки интеграций")).toBeInTheDocument();
    expect(screen.getByText("Критично")).toBeInTheDocument(); // overall status badge
  });

  it("sorts categories worst-severity first (critical category leads)", () => {
    renderPanel({ data });
    const cards = screen.getAllByTestId(/^cc-category-/);
    expect(cards[0]).toHaveAttribute("data-testid", "cc-category-high_risk");
  });

  it("shows severity summary chips from alert_count", () => {
    renderPanel({ data });
    const summary = screen.getByTestId("cc-severity-summary");
    expect(within(summary).getByText("Критичные: 1")).toBeInTheDocument();
    expect(within(summary).getByText("Высокие: 2")).toBeInTheDocument();
  });

  it("renders a 'Перейти' link only for internal action_url", () => {
    renderPanel({ data });
    const links = screen.getAllByRole("link", { name: /Перейти/ });
    expect(links).toHaveLength(2); // a1 (/risk) + a2 (/training); a3 has no url
  });

  it("renders empty state when there are no alerts", () => {
    renderPanel({ data: { ...data, status: "ok", alerts: [], alert_count: {} } });
    expect(screen.getByTestId("command-center-empty")).toHaveTextContent("Нет активных алертов");
  });

  it("renders error state and calls onRefresh", async () => {
    const onRefresh = vi.fn();
    renderPanel({ data: null, error: { message: "Network Error" }, onRefresh });
    expect(screen.getByTestId("command-center-error")).toHaveTextContent("Network Error");
    await userEvent.click(screen.getByRole("button", { name: /Обновить/ }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("renders a loading placeholder when there is no data yet", () => {
    renderPanel({ data: null, loading: true });
    expect(screen.getByText(/Загрузка командного центра/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend; npx vitest run src/__tests__/CommandCenterPanel.test.tsx`
Expected: FAIL — cannot resolve `@/components/operational/CommandCenterPanel`.

- [ ] **Step 3: Implement the panel**

Create `frontend/src/components/operational/CommandCenterPanel.tsx`:

```tsx
import { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Info,
  RefreshCw,
  type LucideIcon
} from "lucide-react";
import { Link } from "react-router-dom";

import type {
  AlertCategory,
  AlertItem,
  AlertSeverity,
  OperationalDashboardDto
} from "@/api/operationalDashboard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/utils/cn";

const CATEGORY_LABELS_RU: Record<AlertCategory, string> = {
  overdue: "Просроченные",
  blocked_approval: "Заблокированные согласования",
  integration_error: "Ошибки интеграций",
  high_risk: "Высокий риск",
  health_warning: "Предупреждения системы",
  unassigned_task: "Неназначенные задачи",
  data_quality: "Качество данных"
};

/** Canonical fallback order for categories with equal worst-severity. */
const CATEGORY_ORDER: AlertCategory[] = [
  "overdue",
  "blocked_approval",
  "integration_error",
  "high_risk",
  "health_warning",
  "unassigned_task",
  "data_quality"
];

const SEVERITY_RANK: Record<AlertSeverity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3
};

const SEVERITY_LABELS_RU: Record<AlertSeverity, string> = {
  critical: "Критичные",
  high: "Высокие",
  medium: "Средние",
  low: "Низкие"
};

const SEVERITY_ICON: Record<AlertSeverity, LucideIcon> = {
  critical: AlertCircle,
  high: AlertTriangle,
  medium: Info,
  low: Info
};

const SEVERITY_ICON_CLASS: Record<AlertSeverity, string> = {
  critical: "text-red-500",
  high: "text-amber-500",
  medium: "text-muted-foreground",
  low: "text-muted-foreground"
};

const SEVERITY_SUMMARY_ORDER: AlertSeverity[] = ["critical", "high", "medium", "low"];

const MAX_VISIBLE_PER_CATEGORY = 20;

const isInternalUrl = (url?: string | null): url is string => Boolean(url && url.startsWith("/"));

type CategoryGroup = { category: AlertCategory; alerts: AlertItem[] };

function groupByCategory(alerts: AlertItem[]): CategoryGroup[] {
  const map = new Map<AlertCategory, AlertItem[]>();
  for (const alert of alerts) {
    const list = map.get(alert.category) ?? [];
    list.push(alert);
    map.set(alert.category, list);
  }
  const groups: CategoryGroup[] = Array.from(map.entries()).map(([category, items]) => ({
    category,
    alerts: [...items].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])
  }));
  groups.sort((a, b) => {
    const aWorst = Math.min(...a.alerts.map((i) => SEVERITY_RANK[i.severity]));
    const bWorst = Math.min(...b.alerts.map((i) => SEVERITY_RANK[i.severity]));
    if (aWorst !== bWorst) return aWorst - bWorst;
    return CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category);
  });
  return groups;
}

function AlertRow({ alert }: { alert: AlertItem }) {
  const Icon = SEVERITY_ICON[alert.severity] ?? Info;
  return (
    <div className="flex items-start gap-3 rounded-md border bg-muted/30 p-3" data-testid={`cc-alert-${alert.id}`}>
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", SEVERITY_ICON_CLASS[alert.severity])} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{alert.title}</span>
          <Badge variant="secondary" className="text-xs">
            {alert.count} шт.
          </Badge>
        </div>
        {alert.description ? <p className="mt-0.5 text-xs text-muted-foreground">{alert.description}</p> : null}
        {isInternalUrl(alert.action_url) ? (
          <Link
            to={alert.action_url}
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:underline"
          >
            Перейти <ArrowRight className="h-3 w-3" />
          </Link>
        ) : null}
      </div>
    </div>
  );
}

function AlertCategoryCard({ category, alerts }: CategoryGroup) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? alerts : alerts.slice(0, MAX_VISIBLE_PER_CATEGORY);
  const hidden = alerts.length - visible.length;
  return (
    <Card data-testid={`cc-category-${category}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{CATEGORY_LABELS_RU[category] ?? category}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {visible.map((alert) => (
          <AlertRow key={alert.id} alert={alert} />
        ))}
        {hidden > 0 ? (
          <Button variant="ghost" size="sm" onClick={() => setExpanded(true)}>
            Показать ещё ({hidden})
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

export type CommandCenterPanelProps = {
  data: OperationalDashboardDto | null;
  loading?: boolean;
  error?: { message?: string } | null;
  onRefresh?: () => void;
};

/**
 * Pure presentational command center: data/loading/error come from props, so it
 * is unit-tested directly without mocking a store or the API client.
 */
export function CommandCenterPanel({ data, loading, error, onRefresh }: CommandCenterPanelProps) {
  const groups = data ? groupByCategory(data.alerts) : [];

  return (
    <section className="space-y-4" data-testid="command-center-panel">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">Командный центр</h2>
          {data ? <StatusBadge status={data.status} /> : null}
        </div>
        {onRefresh ? (
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} aria-hidden />
            Обновить
          </Button>
        ) : null}
      </header>

      {data ? (
        <div className="flex flex-wrap gap-2" data-testid="cc-severity-summary">
          {SEVERITY_SUMMARY_ORDER.map((sev) => {
            const n = data.alert_count?.[sev] ?? 0;
            if (!n) return null;
            return (
              <Badge
                key={sev}
                variant={sev === "critical" ? "destructive" : "secondary"}
                className="text-xs"
              >
                {SEVERITY_LABELS_RU[sev]}: {n}
              </Badge>
            );
          })}
        </div>
      ) : null}

      {error ? (
        <Card data-testid="command-center-error">
          <CardContent className="p-4 text-sm text-red-600">
            Не удалось загрузить командный центр{error.message ? `: ${error.message}` : "."}
          </CardContent>
        </Card>
      ) : null}

      {!error && data && data.alerts.length === 0 ? (
        <Card data-testid="command-center-empty">
          <CardContent className="flex items-center gap-2 p-4 text-sm text-emerald-600">
            <CheckCircle2 className="h-4 w-4" aria-hidden />
            Нет активных алертов
          </CardContent>
        </Card>
      ) : null}

      {!error && !data && loading ? (
        <Card>
          <CardContent className="p-4 text-sm text-muted-foreground">Загрузка командного центра…</CardContent>
        </Card>
      ) : null}

      {groups.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {groups.map((group) => (
            <AlertCategoryCard key={group.category} category={group.category} alerts={group.alerts} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

export default CommandCenterPanel;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend; npx vitest run src/__tests__/CommandCenterPanel.test.tsx`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/operational/CommandCenterPanel.tsx frontend/src/__tests__/CommandCenterPanel.test.tsx
git commit -m "feat(w2): CommandCenterPanel presentational component + unit tests"
```

---

## Task 3: Store (Zustand loader)

**Files:**
- Create: `frontend/src/stores/operationalDashboard.ts`

- [ ] **Step 1: Create the store**

```ts
import { create } from "zustand";
import { immer } from "zustand/middleware/immer";

import { operationalDashboardApi, type OperationalDashboardDto } from "@/api/operationalDashboard";
import type { ApiError } from "@/types/dto/common";

interface OperationalDashboardState {
  data: OperationalDashboardDto | null;
  loading: boolean;
  error: ApiError | null;
  fetchDashboard: () => Promise<void>;
  reset: () => void;
}

export const useOperationalDashboardStore = create<OperationalDashboardState>()(
  immer((set) => ({
    data: null,
    loading: false,
    error: null,
    fetchDashboard: async () => {
      set((state) => {
        state.loading = true;
        state.error = null;
      });
      try {
        const data = await operationalDashboardApi.getDashboard();
        set((state) => {
          state.data = data;
        });
      } catch (error) {
        set((state) => {
          state.error = error as ApiError;
        });
      } finally {
        set((state) => {
          state.loading = false;
        });
      }
    },
    reset: () => {
      set(() => ({ data: null, loading: false, error: null }));
    }
  }))
);
```

- [ ] **Step 2: Verify it typechecks**

Run: `npm --prefix frontend run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/operationalDashboard.ts
git commit -m "feat(w2): operational dashboard store (zustand loader)"
```

---

## Task 4: Page (poll timer + visibilitychange)

**Files:**
- Create: `frontend/src/pages/operational/CommandCenterPage.tsx`

- [ ] **Step 1: Create the page**

```tsx
import { useEffect } from "react";

import { CommandCenterPanel } from "@/components/operational/CommandCenterPanel";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { useOperationalDashboardStore } from "@/stores/operationalDashboard";

const POLL_INTERVAL_MS = 30_000;

export function CommandCenterPage() {
  const data = useOperationalDashboardStore((state) => state.data);
  const loading = useOperationalDashboardStore((state) => state.loading);
  const error = useOperationalDashboardStore((state) => state.error);
  const fetchDashboard = useOperationalDashboardStore((state) => state.fetchDashboard);

  useEffect(() => {
    void fetchDashboard();
    const timer = setInterval(() => void fetchDashboard(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchDashboard]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") void fetchDashboard();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [fetchDashboard]);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Командный центр" }]} />
      <CommandCenterPanel
        data={data}
        loading={loading}
        error={error}
        onRefresh={() => void fetchDashboard()}
      />
    </div>
  );
}

export default CommandCenterPage;
```

- [ ] **Step 2: Verify it typechecks**

Run: `npm --prefix frontend run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/operational/CommandCenterPage.tsx
git commit -m "feat(w2): CommandCenterPage with 30s polling + visibilitychange refetch"
```

---

## Task 5: Router + navigation wiring

**Files:**
- Modify: `frontend/src/router/pageRegistry.tsx`
- Modify: `frontend/src/router/routeGroups.tsx`
- Modify: `frontend/src/router/navigationConfig.ts`

- [ ] **Step 1: Register the lazy page**

In `frontend/src/router/pageRegistry.tsx`, add after the `DashboardPage` export (line 4):

```tsx
export const CommandCenterPage = lazy(() => import("@/pages/operational/CommandCenterPage"));
```

- [ ] **Step 2: Add the route to the DASHBOARD_VIEW group**

In `frontend/src/router/routeGroups.tsx`, add `CommandCenterPage` to the import list from `@/router/pageRegistry` (keep alphabetical-ish, e.g. after `ClientPortalRequestsPage`):

```tsx
  CommandCenterPage,
```

Then inside `buildProtectedRouteGroups`, in the `PERMISSIONS.DASHBOARD_VIEW` group's `routes` array (currently ending with the `/workspace/attention` route), add:

```tsx
        <Route key="/command-center" path="/command-center" element={<CommandCenterPage />} />,
```

So the group's routes array becomes:

```tsx
      routes: [
        <Route key="/dashboard" path="/dashboard" element={<DashboardPage />} />,
        <Route key="/dashboard/executive" path="/dashboard/executive" element={<ExecutiveDashboardPage />} />,
        <Route key="/dashboard/safety" path="/dashboard/safety" element={<SafetyDashboardPage />} />,
        <Route key="/dashboard/training" path="/dashboard/training" element={<TrainingDashboardPage />} />,
        <Route key="/dashboard/ppe" path="/dashboard/ppe" element={<PpeDashboardPage />} />,
        <Route key="/dashboard/client-delivery" path="/dashboard/client-delivery" element={<ClientDeliveryDashboardPage />} />,
        <Route key="/command-center" path="/command-center" element={<CommandCenterPage />} />,
        <Route key="/workspace/attention" path="/workspace/attention" element={<WorkspaceAttentionPage />} />
      ]
```

- [ ] **Step 3: Add the nav item**

In `frontend/src/router/navigationConfig.ts`, in the `"Документооборот"` group's `items` array, add right after the `"Центр внимания"` item (which uses `to: "/workspace/attention"`):

```ts
      { label: "Командный центр", to: "/command-center", icon: ShieldAlert, permission: PERMISSIONS.DASHBOARD_VIEW },
```

(`ShieldAlert` is already imported in this file — no new import needed.)

- [ ] **Step 4: Verify typecheck + lint + existing tests**

Run: `npm --prefix frontend run typecheck`
Expected: PASS.

Run: `npm --prefix frontend run lint`
Expected: PASS (0 warnings).

Run: `cd frontend; npx vitest run src/__tests__/CommandCenterPanel.test.tsx`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/router/pageRegistry.tsx frontend/src/router/routeGroups.tsx frontend/src/router/navigationConfig.ts
git commit -m "feat(w2): wire /command-center route + nav item (DASHBOARD_VIEW guard)"
```

---

## Task 6: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Full frontend unit test run**

Run: `cd frontend; npx vitest run`
Expected: PASS — all tests green, including the new `CommandCenterPanel.test.tsx` and the untouched `HealthStatusPanel.test.tsx` (regression-sanity that Health UI is unaffected).

- [ ] **Step 2: Build typecheck**

Run: `npm --prefix frontend run typecheck`
Expected: PASS.

- [ ] **Step 3: Lint**

Run: `npm --prefix frontend run lint`
Expected: PASS (0 warnings).

- [ ] **Step 4: Confirm no stray changes**

Run: `git status -s`
Expected: clean working tree (all changes committed across Tasks 1–5).

---

## Acceptance traceability (spec §7)

- Page `/command-center` with 7 category widgets — Tasks 2, 4, 5.
- Polling 30s + manual refresh + visibilitychange — Task 4 + panel `onRefresh` (Task 2).
- Severity summary, empty/error/loading states, `action_url` links — Task 2.
- Guard `DASHBOARD_VIEW`; roles enforced by backend — Task 5.
- Unit tests green; full suite (incl. Health regression) green — Tasks 2, 6.
- Health UI untouched — no edits to health files anywhere in the plan.
