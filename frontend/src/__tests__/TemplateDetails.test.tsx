import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TemplateDetails } from "@/features/templates/TemplateDetails";

const activateVersionMock = vi.fn();

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
    post: vi.fn()
  }
}));

describe("TemplateDetails", () => {
  it("renders versions and allows activating non-current version", () => {
    render(
      <TemplateDetails
        template={{
          id: "tpl-1",
          code: "order",
          name: "Приказ",
          description: "Шаблон приказа",
          created_at: "2025-01-01T00:00:00Z",
          updated_at: "2025-01-01T00:00:00Z",
          tags: ["ot"],
          current_version: {
            id: "ver-1",
            template_id: "tpl-1",
            version: "1",
            status: "published",
            created_at: "2025-01-01T00:00:00Z",
            updated_at: "2025-01-01T00:00:00Z"
          },
          versions: [
            {
              id: "ver-1",
              template_id: "tpl-1",
              version: "1",
              status: "published",
              created_at: "2025-01-01T00:00:00Z",
              updated_at: "2025-01-01T00:00:00Z"
            },
            {
              id: "ver-2",
              template_id: "tpl-1",
              version: "2",
              status: "published",
              created_at: "2025-01-02T00:00:00Z",
              updated_at: "2025-01-02T00:00:00Z"
            }
          ]
        }}
      />
    );

    expect(screen.getByText("Версия 1")).toBeInTheDocument();
    expect(screen.getByText("Версия 2")).toBeInTheDocument();

    const currentButton = screen.getByRole("button", { name: "Текущая" });
    expect(currentButton).toBeDisabled();

    const activateButton = screen.getByRole("button", { name: "Активировать" });
    expect(activateButton).toBeEnabled();

    fireEvent.click(activateButton);

    expect(activateVersionMock).toHaveBeenCalledWith("tpl-1", "ver-2");
  });
});
