import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CalendarPage from "@/pages/calendar/CalendarPage";
import WorkflowPage from "@/pages/workflow/WorkflowPage";

const getMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn()
  }
}));

describe("Workflow and Calendar operational states", () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it("shows empty state on CalendarPage when no events exist", async () => {
    getMock.mockResolvedValue({ data: [] });

    render(
      <MemoryRouter>
        <CalendarPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/события календаря отсутствуют/i)).toBeInTheDocument();
  });

  it("loads calendar with source from query params", async () => {
    getMock.mockResolvedValue({ data: [] });

    render(
      <MemoryRouter initialEntries={["/calendar?source=training&mode=week"]}>
        <CalendarPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(getMock).toHaveBeenCalledWith("/notifications/calendar/events", {
        params: { source: "training" }
      });
    });
  });

  it("shows workflow empty states when definitions, tasks and instances are empty", async () => {
    getMock.mockImplementation((url: string) => {
      if (["/workflow/definitions", "/workflow/tasks", "/workflow/instances"].includes(url)) {
        return Promise.resolve({ data: [] });
      }
      throw new Error(`Unexpected GET ${url}`);
    });

    render(
      <MemoryRouter>
        <WorkflowPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/нет данных по процессам/i)).toBeInTheDocument();
    expect(screen.getByText(/нет описаний процессов/i)).toBeInTheDocument();
    expect(screen.getByText(/нет экземпляров процессов/i)).toBeInTheDocument();
    expect(screen.getByText(/нет задач процесса/i)).toBeInTheDocument();
  });

  it("shows workflow error state when initial load fails", async () => {
    getMock.mockRejectedValue({ message: "workflow fetch failed" });

    render(
      <MemoryRouter>
        <WorkflowPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("workflow fetch failed");
    });
  });
});