import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrendLineChart } from "@/components/analytics/TrendLineChart";

describe("TrendLineChart", () => {
  it("renders the title and an empty hint when there is no data", () => {
    render(<TrendLineChart title="Инциденты" series={[]} />);
    expect(screen.getByText("Инциденты")).toBeInTheDocument();
    expect(screen.getByText("Нет данных за период")).toBeInTheDocument();
  });

  it("renders a chart container when data is present", () => {
    render(
      <TrendLineChart
        title="Инциденты"
        series={[
          { date: "2026-07-01", value: 2 },
          { date: "2026-07-02", value: 5 },
        ]}
      />,
    );
    expect(screen.getByText("Инциденты")).toBeInTheDocument();
    expect(screen.getByTestId("trend-chart-Инциденты")).toBeInTheDocument();
    expect(screen.queryByText("Нет данных за период")).not.toBeInTheDocument();
  });
});
