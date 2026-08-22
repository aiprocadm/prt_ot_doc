import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AuditPrepPage from "@/pages/audit-prep/AuditPrepPage";
import CorrectiveActionsPage from "@/pages/corrective-actions/CorrectiveActionsPage";
import FindingsPage from "@/pages/findings/FindingsPage";
import PrescriptionsPage from "@/pages/prescriptions/PrescriptionsPage";
import WarehousePage from "@/pages/warehouse/WarehousePage";
import { uxBudgetDelta } from "@/test-utils/uxBudget";

const getPrescriptionsMock = vi.fn();
const getFindingsMock = vi.fn();
const getCorrectiveActionsMock = vi.fn();
const getAuditPrepSnapshotMock = vi.fn();
const listLevelsMock = vi.fn();
const listBatchesMock = vi.fn();
const listMovementsMock = vi.fn();
const listShortagesMock = vi.fn();
const listCountsMock = vi.fn();
const listTransfersMock = vi.fn();
const listLevelsByLocationMock = vi.fn();
const listSuppliersMock = vi.fn();
const getReorderDraftMock = vi.fn();
const listBudgetsMock = vi.fn();

vi.mock("@/api/ops", () => ({
  opsApi: {
    getPrescriptions: (...args: unknown[]) => getPrescriptionsMock(...args),
    getFindings: (...args: unknown[]) => getFindingsMock(...args),
    getCorrectiveActions: (...args: unknown[]) =>
      getCorrectiveActionsMock(...args),
    getAuditPrepSnapshot: (...args: unknown[]) =>
      getAuditPrepSnapshotMock(...args),
  },
}));

vi.mock("@/api/warehouse", () => ({
  warehouseApi: {
    listLevels: (...args: unknown[]) => listLevelsMock(...args),
    listBatches: (...args: unknown[]) => listBatchesMock(...args),
    listMovements: (...args: unknown[]) => listMovementsMock(...args),
    listShortages: (...args: unknown[]) => listShortagesMock(...args),
    listCounts: (...args: unknown[]) => listCountsMock(...args),
    listTransfers: (...args: unknown[]) => listTransfersMock(...args),
    listLevelsByLocation: (...args: unknown[]) =>
      listLevelsByLocationMock(...args),
    listSuppliers: (...args: unknown[]) => listSuppliersMock(...args),
    getReorderDraft: (...args: unknown[]) => getReorderDraftMock(...args),
    listBudgets: (...args: unknown[]) => listBudgetsMock(...args),
  },
}));

describe("operational pages converted from static to real data", () => {
  beforeEach(() => {
    getPrescriptionsMock.mockReset();
    getFindingsMock.mockReset();
    getCorrectiveActionsMock.mockReset();
    getAuditPrepSnapshotMock.mockReset();
    listLevelsMock.mockReset();
    listBatchesMock.mockReset();
    listMovementsMock.mockReset();
    listShortagesMock.mockReset();
    listCountsMock.mockReset();
    listTransfersMock.mockReset();
    listLevelsByLocationMock.mockReset();
    listSuppliersMock.mockReset();
    getReorderDraftMock.mockReset();
    listBudgetsMock.mockReset();
    listMovementsMock.mockResolvedValue([]);
    listShortagesMock.mockResolvedValue([]);
    listCountsMock.mockResolvedValue([]);
    listTransfersMock.mockResolvedValue([]);
    listLevelsByLocationMock.mockResolvedValue([]);
    listSuppliersMock.mockResolvedValue([]);
    getReorderDraftMock.mockResolvedValue({
      groups: [],
      total_lines: 0,
      total_deficit: 0,
    });
    listBudgetsMock.mockResolvedValue([]);
  });

  it("renders warehouse stock levels from the warehouse API", async () => {
    listLevelsMock.mockResolvedValue([
      {
        item_id: "item-1",
        item_name: "Каска",
        total_quantity: 12,
        batch_count: 2,
        nearest_certificate_expiry: "2026-04-01",
      },
    ]);
    listBatchesMock.mockResolvedValue([
      {
        id: "batch-1",
        item_id: "item-1",
        batch_no: "B-001",
        quantity: 12,
        received_at: "2026-01-01",
        certificate_no: "C-1",
        certificate_expires_at: "2026-04-01",
        location: "A1",
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
      },
    ]);

    render(<WarehousePage />);

    expect(await screen.findByText("Каска")).toBeInTheDocument();
    expect(screen.getByText("Партий: 1")).toBeInTheDocument();
  });

  it("filters prescriptions loaded from API", async () => {
    getPrescriptionsMock.mockResolvedValue([
      {
        id: "pr-1",
        inspection_id: "insp-1",
        description: "Закрыть замечание по вентиляции",
        status: "open",
        due_at: "2026-04-10",
      },
      {
        id: "pr-2",
        inspection_id: "insp-2",
        description: "Обновить журнал",
        status: "closed",
        due_at: null,
      },
    ]);

    render(<PrescriptionsPage />);

    expect(
      await screen.findByText(/Закрыть замечание по вентиляции/),
    ).toBeInTheDocument();

    await userEvent.type(
      screen.getByPlaceholderText(/Поиск по описанию/),
      "вентиляции",
    );

    await waitFor(() => {
      expect(screen.queryByText(/Обновить журнал/)).not.toBeInTheDocument();
    });
  });

  it("renders findings from live API instead of static demo rows", async () => {
    getFindingsMock.mockResolvedValue([
      {
        id: "f-1",
        title: "Нет ограждения",
        status: "open",
        severity: "critical",
        source_type: "inspection",
        source_id: "insp-1",
        finding_type: "nonconformity",
        due_date: "2026-04-15",
      },
      {
        id: "f-2",
        title: "Просрочен журнал",
        status: "resolved",
        severity: "medium",
        source_type: "incident",
        source_id: "inc-1",
        finding_type: "observation",
        due_date: null,
      },
    ]);

    render(<FindingsPage />);

    expect(await screen.findByText("Нет ограждения")).toBeInTheDocument();

    await userEvent.type(
      screen.getByPlaceholderText(/Поиск по title/),
      "ограждения",
    );

    await waitFor(() => {
      expect(screen.queryByText("Просрочен журнал")).not.toBeInTheDocument();
    });
  });

  it("renders corrective actions from live API with effectiveness status", async () => {
    getCorrectiveActionsMock.mockResolvedValue([
      {
        id: "ca-1",
        title: "Поменять СИЗ",
        status: "overdue",
        source_type: "prescription",
        source_id: "pr-1",
        action_type: "corrective",
        due_date: "2026-04-10",
        effectiveness_status: null,
      },
      {
        id: "ca-2",
        title: "Провести инструктаж",
        status: "verified",
        source_type: "finding",
        source_id: "f-1",
        action_type: "preventive",
        due_date: "2026-04-20",
        effectiveness_status: "effective",
      },
    ]);

    render(<CorrectiveActionsPage />);

    expect(await screen.findByText("Поменять СИЗ")).toBeInTheDocument();
    expect(screen.getByText("effective")).toBeInTheDocument();
  });

  it("renders audit prep package projection from live snapshot", async () => {
    getAuditPrepSnapshotMock.mockResolvedValue({
      inspections: [
        {
          id: "insp-1",
          authority: "Ростехнадзор",
          scheduled_at: "2026-05-01",
          status: "scheduled",
          inspection_type: "planned",
        },
      ],
      prescriptions: [
        {
          id: "pr-1",
          inspection_id: "insp-1",
          description: "Исправить пробел",
          status: "open",
          due_at: "2026-04-12",
        },
      ],
      overdueTasks: [
        {
          id: "tsk-1",
          title: "Собрать пакет",
          status: "open",
          priority: "high",
          overdue: true,
        },
      ],
    });

    render(
      <MemoryRouter>
        <AuditPrepPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Ростехнадзор")).toBeInTheDocument();
    expect(screen.getByText(/1 предписаний/)).toBeInTheDocument();
  });

  // Приёмка UX-бюджета (ТЗ разд. 59.2, BIZ-60 волна 5): меряем ОТРИСОВАННЫЙ
  // наполненный экран — после ожидания данных из моков, как остальные тесты
  // файла. Пустой экран ничего не доказал бы: колонки и кнопки живут в ветке
  // registry.total > 0.

  it("PrescriptionsPage в UX-бюджете (BIZ-60)", async () => {
    getPrescriptionsMock.mockResolvedValue([
      {
        id: "pr-1",
        inspection_id: "insp-1",
        description: "Закрыть замечание по вентиляции",
        status: "open",
        due_at: "2026-04-10",
      },
    ]);

    render(<PrescriptionsPage />);
    expect(
      await screen.findByText(/Закрыть замечание по вентиляции/),
    ).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "PrescriptionsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("FindingsPage в UX-бюджете (BIZ-60)", async () => {
    getFindingsMock.mockResolvedValue([
      {
        id: "f-1",
        title: "Нет ограждения",
        status: "open",
        severity: "critical",
        source_type: "inspection",
        source_id: "insp-1",
        finding_type: "nonconformity",
        due_date: "2026-04-15",
      },
    ]);

    render(<FindingsPage />);
    expect(await screen.findByText("Нет ограждения")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "FindingsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("CorrectiveActionsPage в UX-бюджете (BIZ-60)", async () => {
    getCorrectiveActionsMock.mockResolvedValue([
      {
        id: "ca-1",
        title: "Поменять СИЗ",
        status: "overdue",
        source_type: "prescription",
        source_id: "pr-1",
        action_type: "corrective",
        due_date: "2026-04-10",
        effectiveness_status: "effective",
      },
    ]);

    render(<CorrectiveActionsPage />);
    expect(await screen.findByText("Поменять СИЗ")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "CorrectiveActionsPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });

  it("AuditPrepPage в UX-бюджете (BIZ-60)", async () => {
    getAuditPrepSnapshotMock.mockResolvedValue({
      inspections: [
        {
          id: "insp-1",
          authority: "Ростехнадзор",
          scheduled_at: "2026-05-01",
          status: "scheduled",
          inspection_type: "planned",
        },
      ],
      prescriptions: [
        {
          id: "pr-1",
          inspection_id: "insp-1",
          description: "Исправить пробел",
          status: "open",
          due_at: "2026-04-12",
        },
      ],
      overdueTasks: [
        {
          id: "tsk-1",
          title: "Собрать пакет",
          status: "open",
          priority: "high",
          overdue: true,
        },
      ],
    });

    render(
      <MemoryRouter>
        <AuditPrepPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Ростехнадзор")).toBeInTheDocument();

    const budget = uxBudgetDelta(document.body, "AuditPrepPage");
    expect(budget.unexpected).toEqual([]);
    expect(budget.stale).toEqual([]);
  });
});
