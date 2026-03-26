import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { TemplateDetails } from "@/features/templates/TemplateDetails";
import type { TemplateDto } from "@/types/dto/templates";

const activateVersionMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/stores/templates", () => ({
  useTemplatesStore: () => ({
    activateVersion: activateVersionMock
  })
}));

vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => ({
    can: () => true
  })
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => postMock(...args)
  }
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  }
}));

describe("TemplateDetails", () => {
  const template: TemplateDto = {
    id: "tpl-1",
    code: "order",
    name: "Приказ",
    description: "Шаблон приказа",
    template_type: "order",
    scope: { type: "site", company_id: "cmp-1", site_id: "site-1" },
    version: 1,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    current_version: {
      id: "ver-1",
      template_id: "tpl-1",
      version: 1,
      status: "active",
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-01T00:00:00Z"
    },
    versions: [
      {
        id: "ver-1",
        template_id: "tpl-1",
        version: 1,
        status: "active",
        created_at: "2025-01-01T00:00:00Z",
        updated_at: "2025-01-01T00:00:00Z"
      },
      {
        id: "ver-2",
        template_id: "tpl-1",
        version: 2,
        status: "active",
        created_at: "2025-01-02T00:00:00Z",
        updated_at: "2025-01-02T00:00:00Z"
      }
    ]
  };

  beforeEach(() => {
    activateVersionMock.mockReset();
    postMock.mockReset();
    vi.mocked(toast.success).mockReset();
    vi.mocked(toast.error).mockReset();
  });

  it("renders versions and allows activating non-current version", async () => {
    render(
      <TemplateDetails template={template} />
    );

    expect(screen.getByText("Версия 1")).toBeInTheDocument();
    expect(screen.getByText("Версия 2")).toBeInTheDocument();

    const currentButton = screen.getByRole("button", { name: "Текущая" });
    expect(currentButton).toBeDisabled();

    expect(screen.getByRole("tab", { name: "Upload/Lint/Preview" })).toBeInTheDocument();

    const activateButton = screen.getByRole("button", { name: "Активировать" });
    expect(activateButton).toBeEnabled();

    fireEvent.click(activateButton);

    await waitFor(() => {
      expect(activateVersionMock).toHaveBeenCalledWith("tpl-1", "ver-2");
    });
  });

  it("shows toast instead of crashing when preview JSON is invalid", async () => {
    const user = userEvent.setup();

    render(<TemplateDetails template={template} />);

    await user.click(screen.getByRole("tab", { name: "Upload/Lint/Preview" }));
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: "{" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
    expect(postMock).not.toHaveBeenCalledWith("/templates/tpl-1/versions/ver-1:preview", expect.anything());
  });

  it("shows toast when activation fails", async () => {
    activateVersionMock.mockRejectedValueOnce(new Error("activate failed"));

    render(<TemplateDetails template={template} />);

    fireEvent.click(screen.getByRole("button", { name: "Активировать" }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("activate failed");
    });
  });
});
