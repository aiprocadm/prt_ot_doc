import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "@/pages/dashboard/DashboardPage";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";

const fetchSummaryMock = vi.fn();
const fetchOperationalMock = vi.fn();

vi.mock("@/stores/dashboard", () => ({
  useDashboardStore: () => ({
    summary: {
      overdue_tasks: 3,
      critical_obligations: 2,
      incidents_open: 1,
      risks_total: 4,
      training: { total: 5, overdue: 1, due_soon: 2, status: "warning" },
      generated_at: "2024-01-01T00:00:00Z"
    },
    operational: {
      tasks: [
        { id: "task-1", title: "Согласовать пакет", owner_label: "Иванова", due_at: "2026-03-25T00:00:00Z", priority: "high", status: "open", overdue: false }
      ],
      documents: [
        { id: "run-1", title: "Журнал инструктажей", route_label: "Готов", status: "done", risk: "low", created_at: "2026-03-20T00:00:00Z" }
      ],
      readiness: {
        packages_total: 2,
        open_gaps: 1,
        critical_gaps: 0,
        latest_target_date: "2026-04-01",
        readiness_score: 90,
        reasons: ["Есть незакрытые gaps: 1."]
      },
      generated_at: "2026-03-21T00:00:00Z"
    },
    loading: false,
    operationalLoading: false,
    error: null,
    operationalError: null,
    fetchSummary: fetchSummaryMock,
    fetchOperational: fetchOperationalMock
  })
}));

vi.mock("@/components/common/AttentionPanel", () => ({
  AttentionPanel: () => <div data-testid="attention-panel">attention panel</div>
}));

vi.mock("@/hooks/useAsyncResource", () => ({
  useAsyncResource: () => ({
    data: {
      total: 2,
      overdue: 1,
      items: [
        {
          id: "task-overdue-1",
          title: "Просроченная задача",
          status: "open",
          priority: "critical",
          due_at: "2026-03-20T00:00:00Z",
          assignee_id: "user-1",
          entity_type: "training_plan",
          entity_id: "task-overdue-1",
          overdue: true
        },
        {
          id: "task-active-1",
          title: "Активная задача",
          status: "in_progress",
          priority: "medium",
          due_at: "2026-03-30T00:00:00Z",
          assignee_id: "user-2",
          entity_type: "task",
          entity_id: "task-active-1",
          overdue: false
        }
      ]
    },
    loading: false,
    error: null,
    reload: vi.fn()
  })
}));

describe("DashboardPage", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: "dashboard-user",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "dashboard@example.com",
        full_name: "Dashboard User",
        roles: ["super_admin"],
        permissions: [PERMISSIONS.DASHBOARD_VIEW, PERMISSIONS.DOCUMENT_CREATE, PERMISSIONS.PACK_VIEW],
        attributes: { tenant_id: "tenant-1" }
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });
  });

  it("renders KPI values from summary and workspace task inbox filters", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    expect(fetchSummaryMock).toHaveBeenCalled();
    expect(fetchOperationalMock).toHaveBeenCalled();
    expect(screen.getByText("Просроченные задачи")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Инциденты и риски")).toBeInTheDocument();
    expect(screen.getByText("1 / 4")).toBeInTheDocument();
    const taskInbox = screen.getByTestId("workspace-task-inbox");
    expect(within(taskInbox).getByText("Просроченная задача")).toBeInTheDocument();
    expect(within(taskInbox).getByText("Активная задача")).toBeInTheDocument();
    expect(screen.getByTestId("attention-panel")).toBeInTheDocument();
    const overdueLinks = screen.getAllByRole("link", { name: "Просроченная задача" });
    expect(
      overdueLinks.some((link) => {
        const href = link.getAttribute("href") ?? "";
        return href.includes("/tasks?")
          && href.includes("overdue=true")
          && href.includes("priority=critical")
          && href.includes("task_id=task-overdue-1")
          && href.includes("entity_type=training_plan")
          && href.includes("entity_id=task-overdue-1");
      })
    ).toBe(true);
    expect(screen.getByText("Недавние объекты и черновики")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть запуски" })).toHaveAttribute("href", "/pipelines/runs");
    expect(screen.getByRole("link", { name: "Создать документ" })).toHaveAttribute("href", "/documents/wizard");
    expect(screen.getByRole("link", { name: "Запустить мастер" })).toHaveAttribute("href", "/packs");
    expect(within(taskInbox).getByRole("link", { name: "training_plan" })).toHaveAttribute("href", "/training");
    expect(screen.getByRole("link", { name: "Контекст: training_plan" })).toHaveAttribute("href", "/training");

    await user.selectOptions(screen.getByLabelText("Фильтр задач по статусу"), "overdue");
    expect(within(taskInbox).getByText("Просроченная задача")).toBeInTheDocument();
    expect(within(taskInbox).queryByText("Активная задача")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Фильтр задач по статусу"), "all");
    await user.selectOptions(screen.getByLabelText("Фильтр задач по приоритету"), "normal");
    expect(within(taskInbox).queryByText("Просроченная задача")).not.toBeInTheDocument();
    expect(within(taskInbox).getByText("Активная задача")).toBeInTheDocument();
  });

  it("shows disabled quick actions without document create permission", () => {
    useAuthStore.setState((state) => ({
      ...state,
      user: state.user
        ? {
            ...state.user,
            permissions: [PERMISSIONS.DASHBOARD_VIEW]
          }
        : null
    }));

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    expect(screen.getByRole("button", { name: "Создать документ" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Запустить мастер" })).toBeDisabled();
  });

  it("keeps wizard action permission-aware when pack access is missing", () => {
    useAuthStore.setState((state) => ({
      ...state,
      user: state.user
        ? {
            ...state.user,
            permissions: [PERMISSIONS.DASHBOARD_VIEW, PERMISSIONS.DOCUMENT_CREATE]
          }
        : null
    }));

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    expect(screen.getByRole("link", { name: "Создать документ" })).toHaveAttribute("href", "/documents/wizard");
    expect(screen.getByRole("button", { name: "Запустить мастер" })).toBeDisabled();
  });
});
