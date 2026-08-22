import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkflowPage from "@/pages/workflow/WorkflowPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

vi.mock("@/components/permissions/Can", () => ({
  Can: ({
    children,
  }: {
    children: React.ReactNode | ((allowed: boolean) => React.ReactNode);
  }) => <>{typeof children === "function" ? children(true) : children}</>,
}));

describe("workflow action states", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
  });

  it("shows action error and keeps draft form when create workflow definition fails", async () => {
    getMock.mockImplementation((url: string) => {
      if (
        [
          "/workflow/definitions",
          "/workflow/tasks",
          "/workflow/instances",
        ].includes(url)
      ) {
        return Promise.resolve({ data: [] });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
    postMock.mockRejectedValueOnce({
      status: 400,
      message: "create workflow failed",
    });

    render(
      <MemoryRouter>
        <WorkflowPage />
      </MemoryRouter>,
    );

    await screen.findByText(/нет данных по процессам/i);
    fireEvent.change(screen.getByPlaceholderText("Код процесса"), {
      target: { value: "custom-flow" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Создать черновик" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "create workflow failed",
      );
    });
    expect(screen.getByPlaceholderText("Код процесса")).toHaveValue(
      "custom-flow",
    );
  });

  it("shows task action error and keeps task list visible when complete fails", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/workflow/definitions") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/workflow/tasks") {
        return Promise.resolve({
          data: [
            {
              id: "task-1",
              title: "Approve document",
              instance_id: "inst-1",
              node_id: "approval",
              status: "open",
              assignee_role_code: "admin",
              due_at: null,
            },
          ],
        });
      }
      if (url === "/workflow/instances") {
        return Promise.resolve({ data: [] });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
    postMock.mockRejectedValueOnce({ status: 400, message: "complete failed" });

    render(
      <MemoryRouter>
        <WorkflowPage />
      </MemoryRouter>,
    );

    await screen.findByText("Approve document");
    fireEvent.click(screen.getByRole("button", { name: "Завершить" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("complete failed");
    });
    expect(screen.getByText("Approve document")).toBeInTheDocument();
  });

  it("наполненный экран укладывается в UX-бюджет (BIZ-60)", async () => {
    // Меряем экран С ДАННЫМИ: определение с черновой версией (виден полный
    // набор кнопок версии), экземпляр и открытая задача (виден полный набор
    // действий строки задачи). Пустой экран ничего не доказал бы — кнопки
    // строк рождаются только вместе со строками.
    getMock.mockImplementation((url: string) => {
      if (url === "/workflow/definitions") {
        return Promise.resolve({
          data: [
            {
              id: "def-1",
              code: "document-approval-v1",
              name: "Document approval",
              entity_type: "document",
              versions: [
                {
                  id: "ver-1",
                  version_no: 1,
                  status: "draft",
                  graph_json: {
                    nodes: [
                      { id: "start", type: "start", name: "Старт" },
                      { id: "approval", type: "approval", name: "Согласование" },
                      { id: "end", type: "end", name: "Завершение" },
                    ],
                    transitions: [
                      { from: "start", to: "approval" },
                      { from: "approval", to: "end" },
                    ],
                  },
                },
              ],
            },
          ],
        });
      }
      if (url === "/workflow/tasks") {
        return Promise.resolve({
          data: [
            {
              id: "task-1",
              title: "Approve document",
              instance_id: "inst-1",
              node_id: "approval",
              status: "open",
              assignee_role_code: "admin",
              due_at: "2026-08-22T10:00:00Z",
              task_payload: { document_id: "doc-1" },
            },
          ],
        });
      }
      if (url === "/workflow/instances") {
        return Promise.resolve({
          data: [
            {
              id: "inst-1",
              definition_id: "def-1",
              definition_version_id: "ver-1",
              entity_type: "document",
              entity_id: "doc-1",
              status: "active",
              current_node_id: "approval",
              correlation_id: null,
              open_tasks: 1,
              updated_at: "2026-08-22T10:00:00Z",
            },
          ],
        });
      }
      throw new Error(`Unexpected GET ${url}`);
    });

    render(
      <MemoryRouter>
        <WorkflowPage />
      </MemoryRouter>,
    );

    await screen.findByText("Approve document");
    await screen.findByText("Document approval");

    const budget = uxBudgetDelta(document.body, "WorkflowPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
