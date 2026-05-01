import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

import { JobTimeline } from "@/components/JobTimeline";
import type { PipelineStepRun } from "@/api/pipelines";

describe("JobTimeline", () => {
  it("renders empty state for no steps", () => {
    render(<JobTimeline steps={[]} />);
    // Component renders div with space-y-2, so should be present
    const container = screen.getByRole("presentation", { hidden: true });
    expect(container).toBeInTheDocument();
  });

  it("renders single step with success status", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-1",
        step_code: "template",
        status: "success",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:05Z",
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<JobTimeline steps={steps} />);

    expect(screen.getByText("template")).toBeInTheDocument();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText(/attempt: 1/)).toBeInTheDocument();
  });

  it("renders step with failed status and error", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-2",
        step_code: "replace",
        status: "failed",
        attempt: 2,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:10Z",
        error_code: "INVALID_TEMPLATE",
        error_payload: { detail: "Template not found" }
      } as unknown as PipelineStepRun
    ];

    render(<JobTimeline steps={steps} />);

    expect(screen.getByText("replace")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText("INVALID_TEMPLATE")).toBeInTheDocument();
  });

  it("renders duration correctly", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-3",
        step_code: "pdf",
        status: "success",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:30Z",
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<JobTimeline steps={steps} />);

    expect(screen.getByText(/30 c/)).toBeInTheDocument();
  });

  it("renders multiple steps in order", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-1",
        step_code: "template",
        status: "success",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:05Z",
        error_code: null,
        error_payload: null
      },
      {
        step_run_id: "step-2",
        step_code: "headers",
        status: "success",
        attempt: 1,
        started_at: "2026-05-01T10:00:05Z",
        ended_at: "2026-05-01T10:00:10Z",
        error_code: null,
        error_payload: null
      },
      {
        step_run_id: "step-3",
        step_code: "pdf",
        status: "running",
        attempt: 1,
        started_at: "2026-05-01T10:00:10Z",
        ended_at: null,
        error_code: null,
        error_payload: null
      }
    ] as unknown as PipelineStepRun[];

    render(<JobTimeline steps={steps} />);

    expect(screen.getByText("template")).toBeInTheDocument();
    expect(screen.getByText("headers")).toBeInTheDocument();
    expect(screen.getByText("pdf")).toBeInTheDocument();
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  it("handles step without start/end times", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-4",
        step_code: "pending",
        status: "pending",
        attempt: 1,
        started_at: null,
        ended_at: null,
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<JobTimeline steps={steps} />);

    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(screen.getByText(/—/)).toBeInTheDocument(); // Duration should be —
  });

  it("renders step with artifacts in output", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-5",
        step_code: "pdf",
        status: "success",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:05Z",
        error_code: null,
        error_payload: null,
        output: {
          artifacts: {
            document_url: "https://example.com/doc.pdf",
            receipt_url: "https://example.com/receipt.pdf"
          }
        }
      } as unknown as PipelineStepRun
    ];

    render(<JobTimeline steps={steps} />);

    expect(screen.getByText("Артефакты")).toBeInTheDocument();
    expect(screen.getByText("document_url")).toBeInTheDocument();
    expect(screen.getByText("receipt_url")).toBeInTheDocument();
  });

  it("renders cancelled status badge", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-6",
        step_code: "archive",
        status: "canceled",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:02Z",
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<JobTimeline steps={steps} />);

    expect(screen.getByText("canceled")).toBeInTheDocument();
  });
});
