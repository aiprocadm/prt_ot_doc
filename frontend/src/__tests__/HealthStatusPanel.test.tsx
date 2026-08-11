import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { HealthComprehensiveDto } from "@/api/health";
import { HealthStatusPanel } from "@/components/health/HealthStatusPanel";

const data: HealthComprehensiveDto = {
  status: "degraded",
  timestamp: "2026-05-31T00:00:00Z",
  tenant_id: "tenant-1",
  checks: {
    postgres: {
      name: "postgres",
      status: "ok",
      duration_ms: 4.2,
      error: null,
      timestamp: "2026-05-31T00:00:00Z",
    },
    redis: {
      name: "redis",
      status: "ok",
      duration_ms: 1.8,
      error: null,
      timestamp: "2026-05-31T00:00:00Z",
    },
    "1c_integration": {
      name: "1c_integration",
      status: "failed",
      duration_ms: 120,
      error: "connection refused",
      timestamp: "2026-05-31T00:00:00Z",
    },
  },
};

describe("HealthStatusPanel", () => {
  it("renders each dependency check with its human label and the overall status", () => {
    render(<HealthStatusPanel data={data} />);
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Redis")).toBeInTheDocument();
    expect(screen.getByText("Интеграция 1С")).toBeInTheDocument();
    expect(screen.getByText("Деградация")).toBeInTheDocument(); // overall status badge
  });

  it("shows the error message for a failed check and surfaces it first", () => {
    render(<HealthStatusPanel data={data} />);
    const failed = screen.getByTestId("health-check-1c_integration");
    expect(within(failed).getByText("connection refused")).toBeInTheDocument();
    expect(within(failed).getByText("Сбой")).toBeInTheDocument();

    // failed sorts before the healthy checks
    const cards = screen.getAllByTestId(/^health-check-\w+$/);
    expect(cards[0]).toHaveAttribute(
      "data-testid",
      "health-check-1c_integration",
    );
  });

  it("shows probe duration for healthy checks", () => {
    render(<HealthStatusPanel data={data} />);
    const pg = screen.getByTestId("health-check-postgres");
    expect(within(pg).getByText("4 мс")).toBeInTheDocument();
  });

  it("calls onRefresh when the refresh button is clicked", async () => {
    const onRefresh = vi.fn();
    render(<HealthStatusPanel data={data} onRefresh={onRefresh} />);
    await userEvent.click(screen.getByRole("button", { name: /Обновить/ }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("renders an error state when the fetch failed", () => {
    render(
      <HealthStatusPanel data={null} error={{ message: "Network Error" }} />,
    );
    expect(screen.getByTestId("health-status-error")).toHaveTextContent(
      "Network Error",
    );
  });

  it("renders a loading placeholder when there is no data yet", () => {
    render(<HealthStatusPanel data={null} loading />);
    expect(screen.getByText(/Загрузка состояния системы/)).toBeInTheDocument();
  });
});
