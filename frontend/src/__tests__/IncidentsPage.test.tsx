import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const { listMock, createMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  createMock: vi.fn()
}));

const mockIncident = {
  id: "inc-1",
  title: "Падение с высоты",
  incident_type: "injury",
  severity: "high",
  status: "open",
  occurred_at: "2024-06-01T10:00:00Z",
  company_id: "c-1",
  site_id: null,
  description: "Рабочий упал со строительных лесов",
  created_at: "2024-06-01T11:00:00Z",
  updated_at: "2024-06-01T11:00:00Z"
};

vi.mock("@/api/incidents", () => ({
  incidentsApi: {
    list: listMock,
    create: createMock
  }
}));

import IncidentsPage from "@/pages/incidents/IncidentsPage";

describe("IncidentsPage", () => {
  it("renders incidents list after loading", async () => {
    listMock.mockResolvedValue({ items: [mockIncident], total: 1 });

    render(
      <MemoryRouter>
        <IncidentsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Падение с высоты")).toBeInTheDocument();
    });
    expect(listMock).toHaveBeenCalledOnce();
  });

  it("shows empty state when no incidents", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });

    render(
      <MemoryRouter>
        <IncidentsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/инциденты не найдены/i)).toBeInTheDocument();
    });
  });

  it("opens create dialog when button clicked", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <IncidentsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /зарегистрировать инцидент/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /зарегистрировать инцидент/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/заголовок/i)).toBeInTheDocument();
  });
});
