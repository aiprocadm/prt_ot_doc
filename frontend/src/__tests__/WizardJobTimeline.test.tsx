import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

import { WizardJobTimeline } from "@/components/wizard/WizardJobTimeline";
import type { PipelineStepRun } from "@/api/pipelines";

describe("WizardJobTimeline", () => {
  it("renders empty timeline for no steps", () => {
    render(<WizardJobTimeline steps={[]} />);
    // Container should exist even if empty
    const container = screen.queryByText(/./);
    expect(container).not.toBeInTheDocument();
  });

  it("renders single step with queued status", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-1",
        step_code: "template",
        status: "queued",
        attempt: 1,
        started_at: null,
        ended_at: null,
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText("template")).toBeInTheDocument();
    expect(screen.getByText("queued")).toBeInTheDocument();
    expect(screen.getByText(/attempt 1/)).toBeInTheDocument();
  });

  it("renders step with running status", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-2",
        step_code: "headers",
        status: "running",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: null,
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText("headers")).toBeInTheDocument();
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  it("renders step with success status", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-3",
        step_code: "pdf",
        status: "success",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:10Z",
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText("pdf")).toBeInTheDocument();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText(/10 c/)).toBeInTheDocument();
  });

  it("renders step with done status", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-4",
        step_code: "archive",
        status: "done",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:05Z",
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText("archive")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
  });

  it("renders step with failed status and error code", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-5",
        step_code: "replace",
        status: "failed",
        attempt: 2,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:02Z",
        error_code: "VALIDATION_ERROR",
        error_payload: { detail: "Invalid input" }
      } as unknown as PipelineStepRun
    ];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText("replace")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText("VALIDATION_ERROR")).toBeInTheDocument();
    expect(screen.getByText(/attempt 2/)).toBeInTheDocument();
  });

  it("renders step with error status", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-6",
        step_code: "sign",
        status: "error",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:03Z",
        error_code: "CERT_EXPIRED",
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText("sign")).toBeInTheDocument();
    expect(screen.getByText("error")).toBeInTheDocument();
    expect(screen.getByText("CERT_EXPIRED")).toBeInTheDocument();
  });

  it("renders step with canceled status", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-7",
        step_code: "export",
        status: "canceled",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:01Z",
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText("export")).toBeInTheDocument();
    expect(screen.getByText("canceled")).toBeInTheDocument();
  });

  it("renders multiple steps in sequence", () => {
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
        step_code: "replace",
        status: "success",
        attempt: 1,
        started_at: "2026-05-01T10:00:10Z",
        ended_at: "2026-05-01T10:00:15Z",
        error_code: null,
        error_payload: null
      },
      {
        step_run_id: "step-4",
        step_code: "pdf",
        status: "running",
        attempt: 1,
        started_at: "2026-05-01T10:00:15Z",
        ended_at: null,
        error_code: null,
        error_payload: null
      }
    ] as unknown as PipelineStepRun[];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText("template")).toBeInTheDocument();
    expect(screen.getByText("headers")).toBeInTheDocument();
    expect(screen.getByText("replace")).toBeInTheDocument();
    expect(screen.getByText("pdf")).toBeInTheDocument();
  });

  it("calculates duration from started_at to ended_at", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-1",
        step_code: "task",
        status: "success",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:45Z",
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText(/45 c/)).toBeInTheDocument();
  });

  it("shows — for duration when no start time", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-1",
        step_code: "pending",
        status: "queued",
        attempt: 1,
        started_at: null,
        ended_at: null,
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText(/—/)).toBeInTheDocument();
  });

  it("handles unknown status gracefully", () => {
    const steps: PipelineStepRun[] = [
      {
        step_run_id: "step-1",
        step_code: "task",
        status: "unknown_status",
        attempt: 1,
        started_at: "2026-05-01T10:00:00Z",
        ended_at: "2026-05-01T10:00:05Z",
        error_code: null,
        error_payload: null
      } as unknown as PipelineStepRun
    ];

    render(<WizardJobTimeline steps={steps} />);

    expect(screen.getByText("task")).toBeInTheDocument();
    expect(screen.getByText("unknown_status")).toBeInTheDocument();
  });
});
