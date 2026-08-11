import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const { listMyTasksMock, listProcessesMock, edoListMock, signListMock } = vi.hoisted(() => ({
  listMyTasksMock: vi.fn(),
  listProcessesMock: vi.fn(),
  edoListMock: vi.fn(),
  signListMock: vi.fn()
}));

const mockTask = {
  id: "task-1",
  process_id: "proc-1",
  step: "sign",
  assignee_id: "user-1",
  status: "open",
  due_at: "2024-07-01T00:00:00Z",
  created_at: "2024-06-01T10:00:00Z",
  document: { id: "doc-1", name: "Инструкция 001" }
};

vi.mock("@/api/approvals", () => ({
  approvalsApi: {
    listMyTasks: listMyTasksMock,
    listProcesses: listProcessesMock
  }
}));

vi.mock("@/api/edo", () => ({
  edoApi: {
    list: edoListMock
  }
}));

vi.mock("@/api/sign", () => ({
  signApi: {
    list: signListMock
  }
}));

vi.mock("@/components/ApprovalTaskCard", () => ({
  default: ({ task }: { task: { id: string } }) => <div data-testid="task-card">{task.id}</div>
}));

import ApprovalsInboxPage from "@/pages/approvals/ApprovalsInboxPage";

describe("ApprovalsInboxPage", () => {
  it("renders tasks tab and shows task cards", async () => {
    listMyTasksMock.mockImplementation((status: string) =>
      Promise.resolve(status === "open" ? [mockTask] : [])
    );
    listProcessesMock.mockResolvedValue([]);
    edoListMock.mockResolvedValue([]);
    signListMock.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <ApprovalsInboxPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("task-card")).toBeInTheDocument();
    });
  });

  it("shows empty state when all lists are empty", async () => {
    listMyTasksMock.mockResolvedValue([]);
    listProcessesMock.mockResolvedValue([]);
    edoListMock.mockResolvedValue([]);
    signListMock.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <ApprovalsInboxPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/открытых задач нет/i)).toBeInTheDocument();
    });
  });
});
