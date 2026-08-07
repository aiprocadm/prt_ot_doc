import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => apiClientMock.get(...args),
    post: (...args: unknown[]) => apiClientMock.post(...args),
  },
}));

import PipelineBuilderPage from "@/pages/PipelineBuilderPage";

describe("PipelineBuilderPage", () => {
  beforeEach(() => {
    apiClientMock.get.mockReset();
    apiClientMock.post.mockReset();
  });

  it("shows load error for profiles and retries successfully", async () => {
    let shouldFail = true;

    apiClientMock.get.mockImplementation((url: string) => {
      if (url !== "/pipelines/profiles") {
        throw new Error(`Unexpected GET ${url}`);
      }
      if (shouldFail) {
        return Promise.reject({ status: 400, message: "profiles load failed" });
      }
      return Promise.resolve({
        data: [
          {
            id: "profile-1",
            code: "ot-default",
            name: "OT pipeline",
            profile_version: 3,
            graph: {
              nodes: [{ id: "render", type: "render_docx" }],
              edges: [],
            },
          },
        ],
      });
    });

    const user = userEvent.setup();

    await act(async () => {
      render(<PipelineBuilderPage />);
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "profiles load failed",
    );

    shouldFail = false;
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Повторить" }));
    });

    expect(await screen.findByText("ot-default")).toBeInTheDocument();
    expect(screen.getByText(/v3 · OT pipeline/i)).toBeInTheDocument();
  });

  it("shows empty state when no profiles are returned", async () => {
    apiClientMock.get.mockResolvedValue({ data: [] });

    await act(async () => {
      render(<PipelineBuilderPage />);
    });

    expect(
      await screen.findByText(/профили пайплайна не найдены/i),
    ).toBeInTheDocument();
  });

  it("blocks save for duplicate node ids", async () => {
    apiClientMock.get.mockResolvedValue({ data: [] });

    const user = userEvent.setup();

    await act(async () => {
      render(<PipelineBuilderPage />);
    });

    await screen.findByText(/профили пайплайна не найдены/i);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "+ Нода" }));
    });

    const nodeIdInput = await screen.findByDisplayValue("node_5");
    await act(async () => {
      fireEvent.change(nodeIdInput, { target: { value: "headers" } });
    });

    expect(await screen.findByText(/есть дубли id нод/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /сохранить профиль/i }),
    ).toBeDisabled();
    expect(apiClientMock.post).not.toHaveBeenCalled();
  });

  it("saves profile and reloads list", async () => {
    apiClientMock.get
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({
        data: [
          {
            id: "profile-2",
            code: "doc-default",
            name: "Профиль по умолчанию",
            profile_version: 1,
            graph: {
              nodes: [{ id: "render", type: "render_docx" }],
              edges: [{ from: "render", to: "pdf" }],
            },
          },
        ],
      });
    apiClientMock.post.mockResolvedValue({ data: {} });

    const user = userEvent.setup();

    await act(async () => {
      render(<PipelineBuilderPage />);
    });

    await screen.findByText(/профили пайплайна не найдены/i);

    await act(async () => {
      await user.click(
        screen.getByRole("button", { name: /сохранить профиль/i }),
      );
    });

    expect(apiClientMock.post).toHaveBeenCalledWith(
      "/pipelines/profiles",
      expect.objectContaining({
        code: "doc-default",
        name: "Профиль по умолчанию",
        is_active: true,
      }),
    );
    expect(await screen.findByText("doc-default")).toBeInTheDocument();
  });
});
