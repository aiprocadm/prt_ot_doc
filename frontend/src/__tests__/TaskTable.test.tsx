import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TaskTable } from "@/features/tasks/TaskTable";
import { PERMISSIONS } from "@/permissions/permissions";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/stores/tasks", () => ({
  useTasksStore: () => ({
    items: [
      {
        id: "task-1",
        title: "Провести инструктаж",
        status: "open",
        entity_type: "training_plan",
        priority: "high",
        due_at: "2024-01-10",
        updated_at: "2024-01-05",
        overdue: true,
        created_at: "2024-01-01"
      }
    ],
    pagination: { page: 1, page_size: 10, total: 1 },
    list: vi.fn(),
    setPage: vi.fn(),
    setPageSize: vi.fn(),
    loading: false,
    patchTask: vi.fn()
  })
}));

describe("TaskTable", () => {
  const renderTaskTable = () => render(
    <MemoryRouter>
      <TaskTable />
    </MemoryRouter>
  );

  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: "task-user",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "task@example.com",
        full_name: "Task User",
        roles: ["worker"],
        permissions: [PERMISSIONS.TASK_VIEW],
        attributes: { tenant_id: "tenant-1" }
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });
  });

  it("renders overdue indicator", () => {
    renderTaskTable();
    expect(screen.getByText("Просрочено")).toBeInTheDocument();
  });

  it("disables close action for read-only task access", () => {
    renderTaskTable();
    expect(screen.getByTitle("Недостаточно прав")).toBeDisabled();
  });

  it("enables close action when task update permission is granted", () => {
    useAuthStore.setState({
      user: {
        id: "task-manager",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        email: "task.manager@example.com",
        full_name: "Task Manager",
        roles: ["line_manager"],
        permissions: [PERMISSIONS.TASK_VIEW, PERMISSIONS.TASK_UPDATE],
        attributes: { tenant_id: "tenant-1" }
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });

    renderTaskTable();
    expect(screen.getByTitle("Закрыть")).toBeEnabled();
  });
});
