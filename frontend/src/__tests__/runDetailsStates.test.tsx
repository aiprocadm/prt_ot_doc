import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const routeState = vi.hoisted(() => ({ id: "run-1" }));
const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useParams: () => ({ id: routeState.id }),
  };
});

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => apiClientMock.get(...args),
    post: (...args: unknown[]) => apiClientMock.post(...args),
  },
}));

vi.mock("@/components/JobTimeline", () => ({
  JobTimeline: ({ steps }: { steps: Array<{ step_run_id: string }> }) => <div data-testid="job-timeline">{steps.length}</div>,
}));

vi.mock("@/features/files/FileList", () => ({
  FileList: () => <div data-testid="file-list" />,
}));

import PackRunDetailsPage from "@/pages/packs/PackRunDetailsPage";
import PipelineRunDetails from "@/pages/PipelineRunDetails";

const pipelineRun = {
  run_id: "run-1",
  status: "queued",
  profile_id: null,
  created_by: null,
  correlation_id: null,
  inputs_json: null,
  outputs_json: null,
  step_runs: [
    {
      step_run_id: "step-1",
      run_id: "run-1",
      step_code: "render_docx",
      status: "queued",
      attempt: 1,
      started_at: null,
      ended_at: null,
      error_code: null,
      error_payload: null,
      input: null,
      output: null,
    },
  ],
  logs: [],
  artifacts: {},
};

describe("run details operational states", () => {
  beforeEach(() => {
    apiClientMock.get.mockReset();
    apiClientMock.post.mockReset();
    routeState.id = "run-1";

    class MockEventSource {
      onerror: ((this: EventSource, ev: Event) => unknown) | null = null;

      addEventListener = vi.fn();
      close = vi.fn();
    }

    vi.stubGlobal("EventSource", MockEventSource);
  });

  it("reloads PackRunDetailsPage from error state into empty state", async () => {
    routeState.id = "pack-1";
    let shouldFail = true;

    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/pack-runs/pack-1/items" || url === "/pack-runs/pack-1/timeline") {
        if (shouldFail) {
          return Promise.reject({ status: 500, message: "pack load failed" });
        }
        return Promise.resolve({ data: [] });
      }
      throw new Error(`Unexpected GET ${url}`);
    });

    const user = userEvent.setup();
    await act(async () => {
      render(<PackRunDetailsPage />);
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("pack load failed");

    shouldFail = false;
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Повторить" }));
    });

    expect(await screen.findByText(/элементы pack run отсутствуют/i)).toBeInTheDocument();
    expect(screen.getByText(/timeline пуст/i)).toBeInTheDocument();
  });

  it("shows PipelineRunDetails error state instead of hanging on loading and recovers on retry", async () => {
    let shouldFail = true;

    apiClientMock.get.mockImplementation((url: string) => {
      if (url === "/pipelines/runs/run-1") {
        if (shouldFail) {
          return Promise.reject({ status: 500, message: "run load failed" });
        }
        return Promise.resolve({ data: pipelineRun });
      }
      if (url === "/files/entities/job/run-1/files") {
        return Promise.resolve({ data: [] });
      }
      throw new Error(`Unexpected GET ${url}`);
    });

    const user = userEvent.setup();
    await act(async () => {
      render(<PipelineRunDetails />);
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("run load failed");
    await waitFor(() => {
      expect(screen.queryByText(/загрузка pipeline run/i)).not.toBeInTheDocument();
    });

    shouldFail = false;
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Повторить" }));
    });

    expect(await screen.findByText("Job run-1")).toBeInTheDocument();
    expect(screen.getByText(/логи пока отсутствуют/i)).toBeInTheDocument();
    expect(screen.getByTestId("job-timeline")).toHaveTextContent("1");
  });
});