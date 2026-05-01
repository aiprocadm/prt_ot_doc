import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

import ApprovalTimeline from "@/components/ApprovalTimeline";

describe("ApprovalTimeline", () => {
  it("renders empty state when no items", () => {
    render(<ApprovalTimeline items={[]} currentStep={1} />);

    expect(screen.getByText("Решений пока нет")).toBeInTheDocument();
  });

  it("renders timeline header with current step", () => {
    render(<ApprovalTimeline items={[]} currentStep={3} />);

    expect(screen.getByText(/Timeline \(current step: 3\)/)).toBeInTheDocument();
  });

  it("renders single approval decision", () => {
    const items = [
      {
        step_no: 1,
        decision: "Approved",
        comment: "All checks passed"
      }
    ];

    render(<ApprovalTimeline items={items} currentStep={1} />);

    expect(screen.getByText(/Step 1:/)).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText(/All checks passed/)).toBeInTheDocument();
  });

  it("renders multiple approval decisions in order", () => {
    const items = [
      {
        step_no: 1,
        decision: "Approved",
        comment: "Initial review"
      },
      {
        step_no: 2,
        decision: "Rejected",
        comment: "Missing signature"
      },
      {
        step_no: 3,
        decision: "Approved",
        comment: "Signature added"
      }
    ];

    render(<ApprovalTimeline items={items} currentStep={3} />);

    expect(screen.getByText(/Step 1:.*Approved.*Initial review/)).toBeInTheDocument();
    expect(screen.getByText(/Step 2:.*Rejected.*Missing signature/)).toBeInTheDocument();
    expect(screen.getByText(/Step 3:.*Approved.*Signature added/)).toBeInTheDocument();
  });

  it("renders decision without comment", () => {
    const items = [
      {
        step_no: 2,
        decision: "Pending",
        comment: null
      }
    ];

    render(<ApprovalTimeline items={items} currentStep={2} />);

    expect(screen.getByText(/Step 2:.*Pending/)).toBeInTheDocument();
    // Should not have dash when no comment
    const stepText = screen.getByText(/Step 2:/);
    expect(stepText.textContent).toMatch(/^Step 2: Pending$/);
  });

  it("renders decision with undefined comment", () => {
    const items = [
      {
        step_no: 1,
        decision: "Reviewed",
        comment: undefined
      }
    ];

    render(<ApprovalTimeline items={items} currentStep={1} />);

    expect(screen.getByText(/Step 1:.*Reviewed/)).toBeInTheDocument();
  });

  it("renders many timeline steps", () => {
    const items = Array.from({ length: 5 }, (_, i) => ({
      step_no: i + 1,
      decision: i % 2 === 0 ? "Approved" : "Rejected",
      comment: `Comment for step ${i + 1}`
    }));

    render(<ApprovalTimeline items={items} currentStep={5} />);

    for (let i = 0; i < 5; i++) {
      expect(screen.getByText(new RegExp(`Step ${i + 1}:`))).toBeInTheDocument();
    }
  });

  it("renders current step indicator", () => {
    const items = [
      { step_no: 1, decision: "Approved", comment: "Done" },
      { step_no: 2, decision: "In Progress", comment: "Being reviewed" },
      { step_no: 3, decision: "Pending", comment: null }
    ];

    const { rerender } = render(<ApprovalTimeline items={items} currentStep={1} />);
    expect(screen.getByText(/current step: 1/)).toBeInTheDocument();

    rerender(<ApprovalTimeline items={items} currentStep={2} />);
    expect(screen.getByText(/current step: 2/)).toBeInTheDocument();

    rerender(<ApprovalTimeline items={items} currentStep={3} />);
    expect(screen.getByText(/current step: 3/)).toBeInTheDocument();
  });
});
