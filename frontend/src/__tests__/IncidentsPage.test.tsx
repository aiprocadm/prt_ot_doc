import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

const { listMock, createMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  createMock: vi.fn(),
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
  updated_at: "2024-06-01T11:00:00Z",
};

vi.mock("@/api/incidents", () => ({
  incidentsApi: {
    list: listMock,
    create: createMock,
  },
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogTrigger: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  DialogContent: ({ children }: { children: ReactNode }) => (
    <div role="dialog">{children}</div>
  ),
  DialogHeader: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  DialogFooter: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  DialogClose: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

import { PERMISSIONS } from "@/permissions/permissions";
import IncidentsPage from "@/pages/incidents/IncidentsPage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";
import { useAuthStore } from "@/stores/auth";

const userWithIncidentCreate = {
  id: "user-incident-create",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  email: "incident.lead@example.com",
  full_name: "Incident Lead",
  roles: ["worker"],
  permissions: [PERMISSIONS.INCIDENT_VIEW, PERMISSIONS.INCIDENT_CREATE],
  attributes: { tenant_id: "tenant-1" },
};

const userWithoutIncidentCreate = {
  ...userWithIncidentCreate,
  id: "user-incident-view",
  email: "incident.viewer@example.com",
  permissions: [PERMISSIONS.INCIDENT_VIEW],
};

describe("IncidentsPage", () => {
  beforeEach(() => {
    listMock.mockReset();
    createMock.mockReset();
    useAuthStore.setState({
      user: userWithIncidentCreate,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });
  });

  it("renders incidents list after loading", async () => {
    listMock.mockResolvedValue({ items: [mockIncident], total: 1 });

    render(
      <MemoryRouter>
        <IncidentsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Падение с высоты")).toBeInTheDocument();
    });
    expect(screen.getByText("Травма")).toBeInTheDocument();
    expect(listMock).toHaveBeenCalledOnce();
  });

  it("экран в UX-бюджете, или долг записан явно (BIZ-60)", async () => {
    listMock.mockResolvedValue({ items: [mockIncident], total: 1 });

    render(
      <MemoryRouter>
        <IncidentsPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Падение с высоты")).toBeInTheDocument();
    });

    const budget = uxBudgetDelta(document.body, "IncidentsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("initializes status filter from query params", async () => {
    listMock.mockResolvedValue({ items: [mockIncident], total: 1 });

    render(
      <MemoryRouter initialEntries={["/incidents?status=closed"]}>
        <IncidentsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(listMock).toHaveBeenCalledWith({
        limit: 100,
        status_filter: "closed",
      });
    });
  });

  it("shows empty state when no incidents", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });

    render(
      <MemoryRouter>
        <IncidentsPage />
      </MemoryRouter>,
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
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /зарегистрировать инцидент/i }),
      ).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: /зарегистрировать инцидент/i }),
    );

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/заголовок/i)).toBeInTheDocument();
  });

  it("дисциплина показывается словами под событием, неразмеченное — молчит (срез-44)", async () => {
    listMock.mockResolvedValue({
      items: [
        {
          ...mockIncident,
          discipline: "industrial_safety",
          discipline_label: "Промышленная безопасность",
        },
        {
          ...mockIncident,
          id: "inc-2",
          title: "Порез при уборке",
          discipline: null,
          discipline_label: null,
        },
      ],
      total: 2,
    });

    render(
      <MemoryRouter>
        <IncidentsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Порез при уборке")).toBeInTheDocument();
    });
    // Подпись — одна, у размеченного; «не размечено» не превращается в
    // «охрана труда» и не рисуется словами вовсе. Ищем В ТАБЛИЦЕ: тот же
    // текст есть и в списке выбора формы.
    const table = within(screen.getByRole("table"));
    expect(table.getAllByText("Промышленная безопасность")).toHaveLength(1);
    expect(table.queryByText(/охрана труда/i)).not.toBeInTheDocument();
    // Колонок по-прежнему семь: дисциплина не стала восьмой (разд. 59.2).
    expect(table.getAllByRole("columnheader")).toHaveLength(7);
  });

  it("форма регистрации спрашивает дисциплину, пусто — «не размечена» (срез-44)", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <IncidentsPage />
      </MemoryRouter>,
    );

    await user.click(
      await screen.findByRole("button", { name: /зарегистрировать инцидент/i }),
    );

    const select = screen.getByLabelText(/дисциплина/i) as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(
      screen.getByRole("option", { name: "— Не размечена —" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Промышленная безопасность" }),
    ).toBeInTheDocument();
  });

  it("shows disabled create action without create permission", async () => {
    listMock.mockResolvedValue({ items: [], total: 0 });
    useAuthStore.setState({
      user: userWithoutIncidentCreate,
      loading: false,
      error: null,
      isAuthenticated: true,
      initialized: true,
    });

    render(
      <MemoryRouter>
        <IncidentsPage />
      </MemoryRouter>,
    );

    const button = await screen.findByRole("button", {
      name: /зарегистрировать инцидент/i,
    });
    expect(button).toBeDisabled();
  });
});
