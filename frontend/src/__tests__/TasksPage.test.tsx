import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import TasksPage from "@/pages/tasks/TasksPage";

const listMock = vi.fn();
const setFiltersMock = vi.fn();

vi.mock("@/stores/tasks", () => ({
  useTasksStore: () => ({
    list: listMock,
    loading: false,
    filters: {},
    setFilters: setFiltersMock,
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
    pagination: { page: 1, page_size: 10, total: 0 },
    setPage: vi.fn(),
    setPageSize: vi.fn(),
    patchTask: vi.fn()
  })
}));

describe("TasksPage", () => {
  it("applies filters for type and due date", async () => {
    render(
      <MemoryRouter>
        <TasksPage />
      </MemoryRouter>
    );

    expect(listMock).toHaveBeenCalled();

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Тип"), "training_plan");

    expect(setFiltersMock).toHaveBeenCalledWith({ type: "training_plan" });
    expect(listMock).toHaveBeenCalledWith({ type: "training_plan" });

    await user.selectOptions(screen.getByLabelText("Срок"), "overdue");
    expect(setFiltersMock).toHaveBeenCalledWith({ overdue: true });
    expect(listMock).toHaveBeenCalledWith({ overdue: true });
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
