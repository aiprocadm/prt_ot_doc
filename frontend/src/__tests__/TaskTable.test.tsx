import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TaskTable } from "@/features/tasks/TaskTable";

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
    loading: false
  })
}));

describe("TaskTable", () => {
  it("renders overdue indicator", () => {
    render(<TaskTable />);
    expect(screen.getByText("Просрочено")).toBeInTheDocument();
  });
});
