import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CalendarPage from "@/pages/calendar/CalendarPage";
import WorkflowPage from "@/pages/workflow/WorkflowPage";
import type { CalendarEventsResponseDto } from "@/types/dto/calendar";

const getMock = vi.fn();
const getCalendarEventsMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn()
  }
}));

vi.mock("@/api/calendar", () => ({
  calendarApi: {
    getEvents: (...args: unknown[]) => getCalendarEventsMock(...args)
  }
}));

const emptyCalendar: CalendarEventsResponseDto = {
  generated_at: "2026-05-07T10:00:00Z",
  range_from: null,
  range_to: null,
  total: 0,
  overdue_count: 0,
  by_source: [],
  items: []
};

describe("Workflow and Calendar operational states", () => {
  beforeEach(() => {
    getMock.mockReset();
    getCalendarEventsMock.mockReset();
  });

  it("shows empty state on CalendarPage when no events exist", async () => {
    getCalendarEventsMock.mockResolvedValue(emptyCalendar);

    render(
      <MemoryRouter>
        <CalendarPage />
      </MemoryRouter>
    );

    expect(await screen.findByText(/событий в календаре нет/i)).toBeInTheDocument();
  });

  it("forwards source_types and view from query params", async () => {
    getCalendarEventsMock.mockResolvedValue(emptyCalendar);

    render(
      <MemoryRouter initialEntries={["/calendar?view=week&sources=training_session"]}>
        <CalendarPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(getCalendarEventsMock).toHaveBeenCalledWith({
        source_types: ["training_session"],
        person_id: undefined,
        site_id: undefined,
        include_fact: undefined,
        include_sla: undefined
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