import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const { listMock, createMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  createMock: vi.fn()
}));

const mockInspection = {
  id: "insp-1",
  inspection_type: "planned",
  authority: "Роструд",
  status: "planned",
  company_id: "c-1",
  site_id: null,
  purpose: "Плановая проверка условий труда",
  scheduled_at: "2024-07-15T09:00:00Z",
  created_at: "2024-06-01T11:00:00Z",
  updated_at: "2024-06-01T11:00:00Z"
};

vi.mock("@/api/inspections", () => ({
  inspectionsApi: {
    list: listMock,
    create: createMock
  }
}));

import InspectionsPage from "@/pages/inspections/InspectionsPage";

describe("InspectionsPage", () => {
  it("renders inspections list after loading", async () => {
    listMock.mockResolvedValue({ items: [mockInspection], total: 1 });

    render(
      <MemoryRouter>
        <InspectionsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Роструд")).toBeInTheDocument();
    });
    expect(listMock).toHaveBeenCalledOnce();
  });

  it("shows empty state when no inspections", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });

    render(
      <MemoryRouter>
        <InspectionsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/проверки не найдены/i)).toBeInTheDocument();
    });
  });

  it("opens create dialog when button clicked", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <InspectionsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /создать проверку/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /создать проверку/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/орган/i)).toBeInTheDocument();
  });
});
