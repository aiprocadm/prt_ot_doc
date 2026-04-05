import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkflowPage from "@/pages/workflow/WorkflowPage";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  }
}));

vi.mock("@/components/permissions/Can", () => ({
  Can: ({ children }: { children: React.ReactNode | ((allowed: boolean) => React.ReactNode) }) => (
    <>{typeof children === "function" ? children(true) : children}</>
  )
}));

describe("workflow action states", () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
  });

  it("shows action error and keeps draft form when create workflow definition fails", async () => {
    getMock.mockImplementation((url: string) => {
      if (["/workflow/definitions", "/workflow/tasks", "/workflow/instances"].includes(url)) {
        return Promise.resolve({ data: [] });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
    postMock.mockRejectedValueOnce({ status: 400, message: "create workflow failed" });

    render(
      <MemoryRouter>
        <WorkflowPage />
      </MemoryRouter>
    );

    await screen.findByText(/workflow данные отсутствуют/i);
    fireEvent.change(screen.getByPlaceholderText("Код процесса"), { target: { value: "custom-flow" } });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("create workflow failed");
    });
    expect(screen.getByPlaceholderText("Код процесса")).toHaveValue("custom-flow");
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
      </MemoryRouter>
    );

    await screen.findByText("Approve document");
    fireEvent.click(screen.getByRole("button", { name: "Complete" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("complete failed");
    });
    expect(screen.getByText("Approve document")).toBeInTheDocument();
  });
});