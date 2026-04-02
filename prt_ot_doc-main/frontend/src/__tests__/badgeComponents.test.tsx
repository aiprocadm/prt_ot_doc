import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskBadge } from "@/components/common/RiskBadge";
import { SlaIndicator } from "@/components/common/SlaIndicator";
import { StatusBadge } from "@/components/common/StatusBadge";

describe("badge components", () => {
  it("renders risk badge variants and handles missing values", () => {
    const { container: emptyContainer } = render(<RiskBadge />);
    expect(emptyContainer.firstChild).toBeNull();

    render(<RiskBadge level="high" />);
    expect(screen.getByText("high")).toHaveClass("bg-destructive");

    render(<RiskBadge level="unknown" />);
    expect(screen.getByText("unknown")).toHaveClass("bg-secondary");
  });

  it("renders status badge variants and ignores missing status", () => {
    const { container: emptyContainer } = render(<StatusBadge />);
    expect(emptyContainer.firstChild).toBeNull();

    render(<StatusBadge status="error" />);
    expect(screen.getByText("error")).toHaveClass("bg-destructive");

    render(<StatusBadge status="queued" />);
    expect(screen.getByText("queued")).toHaveClass("bg-secondary");
  });

  it("renders SLA indicators with expected styles", () => {
    render(<SlaIndicator status="ok" label="В срок" />);
    expect(screen.getByText("В срок")).toHaveClass("bg-primary");

    render(<SlaIndicator status="warning" label="Предупреждение" />);
    expect(screen.getByText("Предупреждение")).toHaveClass("bg-secondary");
  });
});
