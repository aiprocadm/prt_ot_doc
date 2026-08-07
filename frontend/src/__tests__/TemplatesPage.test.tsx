import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TemplatesPage from "@/pages/templates/TemplatesPage";

const templateStoreState = {
  list: vi.fn(),
  getById: vi.fn(),
  items: [] as Array<{ id: string; name: string }>,
  loading: false,
  error: null as { message: string } | null,
};

const abilityState = {
  can: vi.fn(),
};

vi.mock("@/stores/templates", () => ({
  useTemplatesStore: () => templateStoreState,
}));

vi.mock("@/permissions/useAbility", () => ({
  useAbility: () => abilityState,
}));

vi.mock("@/features/templates/TemplateFormDialog", () => ({
  TemplateFormDialog: ({ trigger }: { trigger: React.ReactNode }) => (
    <div>{trigger}</div>
  ),
}));

vi.mock("@/features/templates/TemplateTable", () => ({
  TemplateTable: ({
    onSelect,
  }: {
    onSelect: (template: { id: string; name: string }) => void;
  }) => (
    <button type="button" onClick={() => onSelect(templateStoreState.items[0])}>
      open template
    </button>
  ),
}));

vi.mock("@/features/templates/TemplateDetails", () => ({
  TemplateDetails: ({ template }: { template: { name: string } }) => (
    <div>details: {template.name}</div>
  ),
}));

describe("TemplatesPage", () => {
  beforeEach(() => {
    templateStoreState.list.mockReset();
    templateStoreState.getById.mockReset();
    templateStoreState.items = [];
    templateStoreState.loading = false;
    templateStoreState.error = null;
    abilityState.can.mockReset();
    abilityState.can.mockImplementation(() => true);
  });

  it("shows access denied when template view permission is missing", () => {
    abilityState.can.mockImplementation(
      (permission: string) => permission !== "template.view",
    );

    render(
      <MemoryRouter>
        <TemplatesPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("Доступ ограничен")).toBeInTheDocument();
    expect(templateStoreState.list).not.toHaveBeenCalled();
  });

  it("shows empty state when no templates are available", async () => {
    render(
      <MemoryRouter>
        <TemplatesPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(templateStoreState.list).toHaveBeenCalled();
    });
    expect(screen.getByText("Шаблоны не найдены")).toBeInTheDocument();
  });

  it("falls back to selected row when getById returns null", async () => {
    templateStoreState.items = [{ id: "tpl-1", name: "Приказ" }];
    templateStoreState.getById.mockResolvedValue(null);

    render(
      <MemoryRouter>
        <TemplatesPage />
      </MemoryRouter>,
    );

    fireEvent.click(
      await screen.findByRole("button", { name: "open template" }),
    );

    await waitFor(() => {
      expect(templateStoreState.getById).toHaveBeenCalledWith("tpl-1");
    });
    expect(screen.getByText("details: Приказ")).toBeInTheDocument();
  });
});
