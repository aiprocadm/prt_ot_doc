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
    items: [],
    pagination: { page: 1, page_size: 10, total: 0 }
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
});
