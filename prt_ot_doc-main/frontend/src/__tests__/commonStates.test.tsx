import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";

describe("common states", () => {
  it("renders EmptyState content", () => {
    render(<EmptyState title="Nothing here" description="Add records to continue" />);

    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Add records to continue")).toBeInTheDocument();
  });

  it("renders ErrorState with contract metadata and field errors", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();

    render(
      <ErrorState
        error={{
          status: 422,
          code: "VALIDATION_ERROR",
          type: "validation",
          message: "Validation failed",
          correlation_id: "corr-123",
          field_errors: [{ field: "template_code", message: "Required" }]
        }}
        onRetry={onRetry}
      />
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Validation failed")).toBeInTheDocument();
    expect(screen.getByText(/Correlation ID: corr-123/)).toBeInTheDocument();
    expect(screen.getByText(/template_code:/)).toBeInTheDocument();
    expect(screen.getByText(/Required/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
