import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import DashboardPage from "@/pages/dashboard/DashboardPage";

const fetchSummaryMock = vi.fn();
const fetchOperationalMock = vi.fn();

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
    operational: {
      tasks: [
        { id: "task-1", title: "Согласовать пакет", owner_label: "Иванова", due_at: "2026-03-25T00:00:00Z", priority: "high", status: "open", overdue: false }
      ],
      documents: [
        { id: "run-1", title: "Журнал инструктажей", route_label: "Готов", status: "done", risk: "low", created_at: "2026-03-20T00:00:00Z" }
      ],
      readiness: {
        packages_total: 2,
        open_gaps: 1,
        critical_gaps: 0,
        latest_target_date: "2026-04-01",
        readiness_score: 90,
        reasons: ["Есть незакрытые gaps: 1."]
      },
      generated_at: "2026-03-21T00:00:00Z"
    },
    loading: false,
    operationalLoading: false,
    error: null,
    operationalError: null,
    fetchSummary: fetchSummaryMock,
    fetchOperational: fetchOperationalMock
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
    expect(fetchOperationalMock).toHaveBeenCalled();
    expect(screen.getByText("Просроченные задачи")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Инциденты и риски")).toBeInTheDocument();
    expect(screen.getByText("1 / 4")).toBeInTheDocument();
    expect(screen.getByText("Согласовать пакет")).toBeInTheDocument();
  });
});
