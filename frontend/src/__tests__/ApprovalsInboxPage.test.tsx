import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const { listMyTasksMock, listProcessesMock, edoListMock, signListMock } =
  vi.hoisted(() => ({
    listMyTasksMock: vi.fn(),
    listProcessesMock: vi.fn(),
    edoListMock: vi.fn(),
    signListMock: vi.fn(),
  }));

const mockTask = {
  id: "task-1",
  process_id: "proc-1",
  step: "sign",
  assignee_id: "user-1",
  status: "open",
  due_at: "2024-07-01T00:00:00Z",
  created_at: "2024-06-01T10:00:00Z",
  document: { id: "doc-1", name: "Инструкция 001" },
};

vi.mock("@/api/approvals", () => ({
  approvalsApi: {
    listMyTasks: listMyTasksMock,
    listProcesses: listProcessesMock,
  },
}));

vi.mock("@/api/edo", () => ({
  edoApi: {
    list: edoListMock,
  },
}));

vi.mock("@/api/sign", () => ({
  signApi: {
    list: signListMock,
  },
}));

// Настоящая карточка, обёрнутая в data-testid: заглушка прятала бы от замера
// UX-бюджета главное содержимое вкладки — кнопки решения и поля комментария.
vi.mock("@/components/ApprovalTaskCard", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/components/ApprovalTaskCard")>();
  const RealCard = actual.default;
  return {
    default: (props: Parameters<typeof RealCard>[0]) => (
      <div data-testid="task-card">
        <RealCard {...props} />
      </div>
    ),
  };
});

import ApprovalsInboxPage from "@/pages/approvals/ApprovalsInboxPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

describe("ApprovalsInboxPage", () => {
  it("renders tasks tab and shows task cards", async () => {
    listMyTasksMock.mockImplementation((status: string) =>
      Promise.resolve(status === "open" ? [mockTask] : []),
    );
    listProcessesMock.mockResolvedValue([]);
    edoListMock.mockResolvedValue([]);
    signListMock.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <ApprovalsInboxPage />
      </MemoryRouter>,
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
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/открытых задач нет/i)).toBeInTheDocument();
    });
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    // Моки в файле per-test, поэтому тест бюджета несёт свои наполненные
    // данные: замер пустого экрана был бы самообманом. Открытая задача рисует
    // настоящую карточку (кнопки решения + поля), закрытая — блок
    // «Выполненные задачи».
    listMyTasksMock.mockImplementation((status: string) =>
      Promise.resolve(
        status === "open"
          ? [mockTask]
          : [{ ...mockTask, id: "task-2", status: "done" }],
      ),
    );
    listProcessesMock.mockResolvedValue([]);
    edoListMock.mockResolvedValue([]);
    signListMock.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <ApprovalsInboxPage />
      </MemoryRouter>,
    );

    await screen.findByRole("button", { name: "Согласовать" });
    await screen.findByText(/Выполненные задачи/);

    const budget = uxBudgetDelta(document.body, "ApprovalsInboxPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
