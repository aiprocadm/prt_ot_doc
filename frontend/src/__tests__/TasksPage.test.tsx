import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { PERMISSIONS } from "@/permissions/permissions";
import TasksPage from "@/pages/tasks/TasksPage";
import { useAuthStore } from "@/stores/auth";

const listMock = vi.fn();
const setFiltersMock = vi.fn();
const patchTaskMock = vi.fn();
const createTaskMock = vi.fn();

const userWithTaskUpdate = {
  id: "task-manager",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  email: "task.manager@example.com",
  full_name: "Task Manager",
  roles: ["line_manager"],
  permissions: [PERMISSIONS.TASK_VIEW, PERMISSIONS.TASK_UPDATE],
  attributes: { tenant_id: "tenant-1" }
};

vi.mock("@/stores/tasks", () => ({
  useTasksStore: () => ({
    list: listMock,
    loading: false,
    error: null,
    filters: {},
    setFilters: setFiltersMock,
    taskFocusLoadError: null,
    clearTaskFocusState: vi.fn(),
    items: [
      {
        id: "task-focus-1",
        title: "Фокусная задача",
        status: "open",
        priority: "high",
        overdue: false,
        entity_type: "document",
        entity_id: "entity-1",
      }
    ],
    item: null,
    getById: vi.fn(),
    createTask: createTaskMock,
    pagination: { page: 1, page_size: 10, total: 0 },
    setPage: vi.fn(),
    setPageSize: vi.fn(),
    patchTask: patchTaskMock
  })
}));

describe("TasksPage", () => {
  it("shows enabled focused-task close action with update permission", async () => {
    patchTaskMock.mockReset();
    useAuthStore.setState({
      user: userWithTaskUpdate,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/tasks?task_id=task-focus-1&entity_type=document&entity_id=entity-1"]}>
        <TasksPage />
      </MemoryRouter>
    );

    const closeButton = await screen.findByRole("button", { name: "Закрыть фокусную задачу" });
    expect(closeButton).toBeEnabled();

    await user.click(closeButton);
    expect(patchTaskMock).toHaveBeenCalledWith("task-focus-1", { status: "done" });
  });

  it("shows disabled focused-task close action without update permission", async () => {
    patchTaskMock.mockReset();
    useAuthStore.setState({
      user: {
        ...userWithTaskUpdate,
        id: "task-viewer",
        email: "task.viewer@example.com",
        permissions: [PERMISSIONS.TASK_VIEW]
      },
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true
    });

    render(
      <MemoryRouter initialEntries={["/tasks?task_id=task-focus-1&entity_type=document&entity_id=entity-1"]}>
        <TasksPage />
      </MemoryRouter>
    );

    const closeButton = await screen.findByRole("button", { name: "Закрыть фокусную задачу" });
    expect(closeButton).toBeDisabled();
  });

  it("applies filters for type and due date", async () => {
    listMock.mockReset();
    setFiltersMock.mockReset();
    render(
      <MemoryRouter>
        <TasksPage />
      </MemoryRouter>
    );

    expect(listMock).toHaveBeenCalled();

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Тип"), "training_plan");

    expect(setFiltersMock).toHaveBeenCalledWith({
      type: "training_plan",
      overdue: undefined,
      priority: undefined
    });
    expect(listMock).toHaveBeenCalledWith({
      type: "training_plan",
      overdue: undefined,
      priority: undefined
    });

    await user.selectOptions(screen.getByLabelText("Срок"), "overdue");
    expect(setFiltersMock).toHaveBeenCalledWith({
      type: "training_plan",
      overdue: true,
      priority: undefined
    });
    expect(listMock).toHaveBeenCalledWith({
      type: "training_plan",
      overdue: true,
      priority: undefined
    });
  });

  it("shows focus card for task context from workspace link", () => {
    render(
      <MemoryRouter initialEntries={["/tasks?task_id=task-focus-1&entity_type=document&entity_id=entity-1"]}>
        <TasksPage />
      </MemoryRouter>
    );

    expect(screen.getByTestId("task-focus-card")).toBeInTheDocument();
    expect(screen.getByText("Фокусная задача · open · high")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть summary сущности" })).toHaveAttribute(
      "href",
      "/documents?entity_type=document&entity_id=entity-1&view=summary"
    );
    expect(screen.getByRole("link", { name: "Открыть timeline сущности" })).toHaveAttribute(
      "href",
      "/documents?entity_type=document&entity_id=entity-1&view=timeline"
    );
    expect(screen.getByRole("link", { name: "Открыть контекст сущности" })).toHaveAttribute("href", "/documents");
  });
});
