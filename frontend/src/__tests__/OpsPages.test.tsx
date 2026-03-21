import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AuditPrepPage from "@/pages/audit-prep/AuditPrepPage";
import CorrectiveActionsPage from "@/pages/corrective-actions/CorrectiveActionsPage";
import FindingsPage from "@/pages/findings/FindingsPage";
import PrescriptionsPage from "@/pages/prescriptions/PrescriptionsPage";
import WarehousePage from "@/pages/warehouse/WarehousePage";

const getPpeOverviewMock = vi.fn();
const getPrescriptionsMock = vi.fn();
const getFindingsMock = vi.fn();
const getCorrectiveActionsMock = vi.fn();
const getAuditPrepSnapshotMock = vi.fn();

vi.mock("@/api/ops", () => ({
  opsApi: {
    getPpeOverview: (...args: unknown[]) => getPpeOverviewMock(...args),
    getPrescriptions: (...args: unknown[]) => getPrescriptionsMock(...args),
    getFindings: (...args: unknown[]) => getFindingsMock(...args),
    getCorrectiveActions: (...args: unknown[]) => getCorrectiveActionsMock(...args),
    getAuditPrepSnapshot: (...args: unknown[]) => getAuditPrepSnapshotMock(...args)
  }
}));

describe("operational pages converted from static to real data", () => {
  beforeEach(() => {
    getPpeOverviewMock.mockReset();
    getPrescriptionsMock.mockReset();
    getFindingsMock.mockReset();
    getCorrectiveActionsMock.mockReset();
    getAuditPrepSnapshotMock.mockReset();
  });

  it("renders warehouse items from PPE overview API", async () => {
    getPpeOverviewMock.mockResolvedValue({
      items: [{ id: "item-1", code: "PPE-001", name: "Каска", category: "helmet", default_wear_days: 365 }],
      issues: [],
      expiring: [{ id: "issue-1", person_id: "p-1", item_id: "item-1", quantity: 1, status: "issued", expires_at: "2026-04-01" }],
      persons: []
    });

    render(<WarehousePage />);

    expect(await screen.findByText("Каска")).toBeInTheDocument();
    expect(screen.getByText("PPE-001")).toBeInTheDocument();
    expect(screen.getByText(/Истекающих выдач: 1/)).toBeInTheDocument();
  });

  it("filters prescriptions loaded from API", async () => {
    getPrescriptionsMock.mockResolvedValue([
      { id: "pr-1", inspection_id: "insp-1", description: "Закрыть замечание по вентиляции", status: "open", due_at: "2026-04-10" },
      { id: "pr-2", inspection_id: "insp-2", description: "Обновить журнал", status: "closed", due_at: null }
    ]);

    render(<PrescriptionsPage />);

    expect(await screen.findByText(/Закрыть замечание по вентиляции/)).toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText(/Поиск по описанию/), "вентиляции");

    await waitFor(() => {
      expect(screen.queryByText(/Обновить журнал/)).not.toBeInTheDocument();
    });
  });


  it("renders findings from live API instead of static demo rows", async () => {
    getFindingsMock.mockResolvedValue([
      { id: "f-1", title: "Нет ограждения", status: "open", severity: "critical", source_type: "inspection", source_id: "insp-1", finding_type: "nonconformity", due_date: "2026-04-15" },
      { id: "f-2", title: "Просрочен журнал", status: "resolved", severity: "medium", source_type: "incident", source_id: "inc-1", finding_type: "observation", due_date: null }
    ]);

    render(<FindingsPage />);

    expect(await screen.findByText("Нет ограждения")).toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText(/Поиск по title/), "ограждения");

    await waitFor(() => {
      expect(screen.queryByText("Просрочен журнал")).not.toBeInTheDocument();
    });
  });

  it("renders corrective actions from live API with effectiveness status", async () => {
    getCorrectiveActionsMock.mockResolvedValue([
      { id: "ca-1", title: "Поменять СИЗ", status: "overdue", source_type: "prescription", source_id: "pr-1", action_type: "corrective", due_date: "2026-04-10", effectiveness_status: null },
      { id: "ca-2", title: "Провести инструктаж", status: "verified", source_type: "finding", source_id: "f-1", action_type: "preventive", due_date: "2026-04-20", effectiveness_status: "effective" }
    ]);

    render(<CorrectiveActionsPage />);

    expect(await screen.findByText("Поменять СИЗ")).toBeInTheDocument();
    expect(screen.getByText("effective")).toBeInTheDocument();
  });

  it("renders audit prep package projection from live snapshot", async () => {
    getAuditPrepSnapshotMock.mockResolvedValue({
      inspections: [{ id: "insp-1", authority: "Ростехнадзор", scheduled_at: "2026-05-01", status: "scheduled", inspection_type: "planned" }],
      prescriptions: [{ id: "pr-1", inspection_id: "insp-1", description: "Исправить пробел", status: "open", due_at: "2026-04-12" }],
      overdueTasks: [{ id: "tsk-1", title: "Собрать пакет", status: "open", priority: "high", overdue: true }]
    });

    render(
      <MemoryRouter>
        <AuditPrepPage />
      </MemoryRouter>
    );

    expect(await screen.findByText("Ростехнадзор")).toBeInTheDocument();
    expect(screen.getByText(/1 предписаний/)).toBeInTheDocument();
  });
});
