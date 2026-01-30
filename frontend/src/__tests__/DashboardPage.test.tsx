import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import DashboardPage from "@/pages/dashboard/DashboardPage";

const fetchSummaryMock = vi.fn();

vi.mock("@/stores/dashboard", () => ({
  useDashboardStore: () => ({
    summary: {
      overdue_tasks: 3,
      critical_obligations: 2,
      incidents_open: 1,
      risks_total: 4,
      training: { total: 5, overdue: 1, due_soon: 2, status: "warning" },
      generated_at: "2024-01-01T00:00:00Z"
    },
    loading: false,
    error: null,
    fetchSummary: fetchSummaryMock
  })
}));

describe("DashboardPage", () => {
  it("renders KPI values from summary", () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    );

    expect(fetchSummaryMock).toHaveBeenCalled();
    expect(screen.getByText("Просроченные задачи")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Инциденты и риски")).toBeInTheDocument();
    expect(screen.getByText("1 / 4")).toBeInTheDocument();
  });
});
