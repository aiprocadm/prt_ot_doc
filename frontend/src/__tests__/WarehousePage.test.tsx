import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WarehousePage from "@/pages/warehouse/WarehousePage";

const listLevelsMock = vi.fn();
const listBatchesMock = vi.fn();
const listMovementsMock = vi.fn();
const createMovementMock = vi.fn();
const listShortagesMock = vi.fn();
const listCountsMock = vi.fn();
const createCountMock = vi.fn();
const getCountMock = vi.fn();
const patchCountLinesMock = vi.fn();
const applyCountMock = vi.fn();
const cancelCountMock = vi.fn();
const listTransfersMock = vi.fn();
const createTransferMock = vi.fn();
const listLevelsByLocationMock = vi.fn();
const listSuppliersMock = vi.fn();
const createSupplierMock = vi.fn();
const updateSupplierMock = vi.fn();
const deleteSupplierMock = vi.fn();
const getReorderDraftMock = vi.fn();
const createBatchMock = vi.fn();
const patchItemPreferredSupplierMock = vi.fn();
const listBudgetsMock = vi.fn();
const getBudgetMock = vi.fn();
const createBudgetMock = vi.fn();

vi.mock("@/api/warehouse", () => ({
  warehouseApi: {
    listLevels: (...args: unknown[]) => listLevelsMock(...args),
    listBatches: (...args: unknown[]) => listBatchesMock(...args),
    listMovements: (...args: unknown[]) => listMovementsMock(...args),
    createMovement: (...args: unknown[]) => createMovementMock(...args),
    listShortages: (...args: unknown[]) => listShortagesMock(...args),
    listCounts: (...args: unknown[]) => listCountsMock(...args),
    createCount: (...args: unknown[]) => createCountMock(...args),
    getCount: (...args: unknown[]) => getCountMock(...args),
    patchCountLines: (...args: unknown[]) => patchCountLinesMock(...args),
    applyCount: (...args: unknown[]) => applyCountMock(...args),
    cancelCount: (...args: unknown[]) => cancelCountMock(...args),
    listTransfers: (...args: unknown[]) => listTransfersMock(...args),
    createTransfer: (...args: unknown[]) => createTransferMock(...args),
    listLevelsByLocation: (...args: unknown[]) => listLevelsByLocationMock(...args),
    listSuppliers: (...args: unknown[]) => listSuppliersMock(...args),
    createSupplier: (...args: unknown[]) => createSupplierMock(...args),
    updateSupplier: (...args: unknown[]) => updateSupplierMock(...args),
    deleteSupplier: (...args: unknown[]) => deleteSupplierMock(...args),
    getReorderDraft: (...args: unknown[]) => getReorderDraftMock(...args),
    createBatch: (...args: unknown[]) => createBatchMock(...args),
    patchItemPreferredSupplier: (...args: unknown[]) => patchItemPreferredSupplierMock(...args),
    listBudgets: (...args: unknown[]) => listBudgetsMock(...args),
    getBudget: (...args: unknown[]) => getBudgetMock(...args),
    createBudget: (...args: unknown[]) => createBudgetMock(...args)
  }
}));

describe("WarehousePage", () => {
  beforeEach(() => {
    listLevelsMock.mockReset();
    listBatchesMock.mockReset();
    listMovementsMock.mockReset();
    createMovementMock.mockReset();
    listShortagesMock.mockReset();
    listCountsMock.mockReset();
    createCountMock.mockReset();
    getCountMock.mockReset();
    patchCountLinesMock.mockReset();
    applyCountMock.mockReset();
    cancelCountMock.mockReset();
    listTransfersMock.mockReset();
    createTransferMock.mockReset();
    listLevelsByLocationMock.mockReset();
    listSuppliersMock.mockReset();
    createSupplierMock.mockReset();
    updateSupplierMock.mockReset();
    deleteSupplierMock.mockReset();
    getReorderDraftMock.mockReset();
    createBatchMock.mockReset();
    patchItemPreferredSupplierMock.mockReset();
    listBudgetsMock.mockReset();
    getBudgetMock.mockReset();
    createBudgetMock.mockReset();
    listMovementsMock.mockResolvedValue([]);
    listShortagesMock.mockResolvedValue([]);
    listCountsMock.mockResolvedValue([]);
    listTransfersMock.mockResolvedValue([]);
    listLevelsByLocationMock.mockResolvedValue([]);
    listSuppliersMock.mockResolvedValue([]);
    getReorderDraftMock.mockResolvedValue({ groups: [], total_lines: 0, total_deficit: 0 });
    listBudgetsMock.mockResolvedValue([]);
  });

  it("renders stock levels from the warehouse API", async () => {
    listLevelsMock.mockResolvedValue([
      { item_id: "i1", item_name: "Каска", total_quantity: 12, batch_count: 2, nearest_certificate_expiry: null }
    ]);
    listBatchesMock.mockResolvedValue([
      { id: "b1", item_id: "i1", batch_no: "B-1", quantity: 12, created_at: "2026-05-29T00:00:00Z", updated_at: "2026-05-29T00:00:00Z" }
    ]);

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Каска")).toBeInTheDocument());
    expect(screen.getByText("Партий: 1")).toBeInTheDocument();
  });

  it("renders recent movements", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listMovementsMock.mockResolvedValue([
      { id: "m1", item_id: "i1", batch_id: "b1", kind: "receipt", quantity_delta: 5, occurred_at: "2026-07-02T00:00:00Z", reason: "поступление", ref_type: null, ref_id: null, created_at: "2026-07-02T00:00:00Z" }
    ]);

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Движения")).toBeInTheDocument());
    expect(screen.getByText("поступление")).toBeInTheDocument();
  });

  it("shows an empty state when there are no levels", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Позиции не найдены")).toBeInTheDocument());
  });

  it("submits a manual movement with the form payload", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listMovementsMock.mockResolvedValue([]);
    createMovementMock.mockResolvedValue({
      id: "m2",
      item_id: "i1",
      batch_id: "b1",
      kind: "receipt",
      quantity_delta: 1,
      occurred_at: "2026-07-02T00:00:00Z",
      reason: null,
      ref_type: null,
      ref_id: null,
      created_at: "2026-07-02T00:00:00Z"
    });

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Движения")).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText("ID партии"), { target: { value: "b1" } });
    fireEvent.click(screen.getByRole("button", { name: "Провести" }));

    await waitFor(() =>
      expect(createMovementMock).toHaveBeenCalledWith(
        expect.objectContaining({ batch_id: "b1", kind: "receipt", quantity: 1, reason: null })
      )
    );
  });

  it("renders the shortage section with a below-threshold row", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listMovementsMock.mockResolvedValue([]);
    listShortagesMock.mockResolvedValue([
      {
        item_id: "i1", item_name: "Каска", min_stock: 10, on_hand: 3, deficit: 7,
        below_threshold: true, avg_daily_consumption: 1, days_to_depletion: 3,
        projected_breach_date: "2026-07-06",
        supplier_id: "s1", supplier_name: "Alpha", supplier_inn: null,
        supplier_contact: null, supplier_source: "explicit"
      }
    ]);

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Дефицит / мин-остаток")).toBeInTheDocument());
    expect(screen.getByText("Каска")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
  });

  it("renders the inventory section with an existing count", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listCountsMock.mockResolvedValue([
      {
        id: "c1", status: "draft", scope_item_id: null, scope_location: null,
        note: "июль", applied_at: null, created_at: "2026-07-03T00:00:00Z",
        line_count: 2, counted_count: 0
      }
    ]);

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Инвентаризация")).toBeInTheDocument());
    expect(screen.getByText("июль")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Открыть" })).toBeInTheDocument();
  });

  it("creates a count and shows its lines", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listCountsMock.mockResolvedValue([]);
    createCountMock.mockResolvedValue({
      id: "c9", status: "draft", scope_item_id: null, scope_location: null,
      note: null, applied_at: null, created_at: "2026-07-03T00:00:00Z",
      line_count: 1, counted_count: 0, diff_count: 0,
      lines: [
        {
          id: "l1", batch_id: "b1", item_id: "i1", batch_no: "B-1", location: null,
          item_name: "Каска", system_qty: 10, counted_qty: null, on_hand: 10,
          delta: null, adjustment_movement_id: null
        }
      ]
    });

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Инвентаризация")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() => expect(createCountMock).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("B-1")).toBeInTheDocument());
  });

  it("creates a stock transfer between locations", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([
      { id: "b1", item_id: "i1", batch_no: "B-1", quantity: 10, location: "A", created_at: "2026-07-04T00:00:00Z", updated_at: "2026-07-04T00:00:00Z" }
    ]);
    listLevelsByLocationMock.mockResolvedValue([
      { item_id: "i1", item_name: "Каска", location: "A", quantity: 10, batch_count: 1 }
    ]);
    createTransferMock.mockResolvedValue({
      ref_id: "r1", item_id: "i1", item_name: "Каска", batch_no: "B-1",
      from_location: "A", to_location: "B", quantity: 3,
      source_batch_id: "b1", dest_batch_id: "d1", out_movement_id: "m1", in_movement_id: "m2",
      reason: null, occurred_at: "2026-07-04T00:00:00Z"
    });

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await screen.findByText(/Перемещения между локациями/i);

    fireEvent.change(screen.getByLabelText(/Партия-источник/i), { target: { value: "b1" } });
    fireEvent.change(screen.getByLabelText(/Куда \(локация\)/i), { target: { value: "B" } });
    fireEvent.change(screen.getByLabelText(/Количество для переноса/i), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: /Перенести/i }));

    await waitFor(() =>
      expect(createTransferMock).toHaveBeenCalledWith({
        source_batch_id: "b1",
        to_location: "B",
        quantity: 3,
        reason: null
      })
    );
  });

  it("renders the suppliers section with an existing supplier", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listSuppliersMock.mockResolvedValue([
      { id: "s1", name: "Alpha", inn: "7701234567", contact_email: null, contact_phone: null }
    ]);

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Поставщики")).toBeInTheDocument());
    expect(screen.getAllByText("Alpha").length).toBeGreaterThan(0);
    expect(screen.getByText("7701234567")).toBeInTheDocument();
  });

  it("creates a supplier from the form", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listSuppliersMock.mockResolvedValue([]);
    createSupplierMock.mockResolvedValue({
      id: "s2", name: "Beta", inn: null, contact_email: null, contact_phone: null
    });

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Поставщики")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Название поставщика/i), { target: { value: "Beta" } });
    fireEvent.click(screen.getByRole("button", { name: /Сохранить поставщика/i }));

    await waitFor(() =>
      expect(createSupplierMock).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Beta" })
      )
    );
  });

  it("renders the reorder draft grouped by supplier", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    getReorderDraftMock.mockResolvedValue({
      groups: [
        {
          supplier_id: "s1",
          supplier_name: "Alpha",
          supplier_inn: null,
          supplier_contact: null,
          lines: [{ item_id: "i1", item_name: "Каска", deficit: 10 }],
          line_count: 1,
          total_deficit: 10
        }
      ],
      total_lines: 1,
      total_deficit: 10
    });

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Дозаказ")).toBeInTheDocument());
    expect(screen.getByText("Каска")).toBeInTheDocument();
    expect(screen.getAllByText("10").length).toBeGreaterThan(0);
  });

  it("patches an item preferred supplier and reloads shortages + reorder draft", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listSuppliersMock.mockResolvedValue([
      { id: "s1", name: "Alpha", inn: null, contact_email: null, contact_phone: null }
    ]);
    listShortagesMock.mockResolvedValue([
      {
        item_id: "i1", item_name: "Каска", min_stock: 10, on_hand: 3, deficit: 7,
        below_threshold: true, avg_daily_consumption: 1, days_to_depletion: 3,
        projected_breach_date: "2026-07-06",
        supplier_id: null, supplier_name: null, supplier_inn: null,
        supplier_contact: null, supplier_source: null
      }
    ]);
    patchItemPreferredSupplierMock.mockResolvedValue(undefined);

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Дефицит / мин-остаток")).toBeInTheDocument());

    const reorderCallsBefore = getReorderDraftMock.mock.calls.length;
    fireEvent.change(screen.getByLabelText(/Предпочтительный поставщик Каска/i), {
      target: { value: "s1" }
    });

    await waitFor(() =>
      expect(patchItemPreferredSupplierMock).toHaveBeenCalledWith("i1", "s1")
    );
    await waitFor(() =>
      expect(getReorderDraftMock.mock.calls.length).toBeGreaterThan(reorderCallsBefore)
    );
  });

  it("escapes CSV cells containing the delimiter when copying the reorder draft", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    getReorderDraftMock.mockResolvedValue({
      groups: [
        {
          supplier_id: "s1",
          supplier_name: "Alpha",
          supplier_inn: null,
          supplier_contact: "mail@x.ru; +7 900 000-00-00",
          lines: [{ item_id: "i1", item_name: "Каска", deficit: 10 }],
          line_count: 1,
          total_deficit: 10
        }
      ],
      total_lines: 1,
      total_deficit: 10
    });

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    const btn = await screen.findByText("Копировать CSV");
    fireEvent.click(btn);

    await waitFor(() => expect(writeText).toHaveBeenCalled());
    const csv = writeText.mock.calls[0][0] as string;
    expect(csv).toContain('"mail@x.ru; +7 900 000-00-00"');
  });

  it("renders the safety budget section with a budget row", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listBudgetsMock.mockResolvedValue([
      { id: "bud-1", name: "Бюджет 2026", period_start: "2026-01-01", period_end: "2026-12-31",
        planned_amount: 100000, notes: null, created_at: "2026-01-01", updated_at: "2026-01-01" }
    ]);
    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    expect(await screen.findByText("Бюджет безопасности")).toBeInTheDocument();
    expect(await screen.findByText("Бюджет 2026")).toBeInTheDocument();
  });

  it("shows computed actual + remaining + unpriced warning on open", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listBudgetsMock.mockResolvedValue([
      { id: "bud-1", name: "Бюджет 2026", period_start: "2026-01-01", period_end: "2026-12-31",
        planned_amount: 100000, notes: null, created_at: "2026-01-01", updated_at: "2026-01-01" }
    ]);
    getBudgetMock.mockResolvedValue({
      id: "bud-1", name: "Бюджет 2026", period_start: "2026-01-01", period_end: "2026-12-31",
      planned_amount: 100000, notes: null, created_at: "2026-01-01", updated_at: "2026-01-01",
      actual_total: 30000, remaining: 70000,
      by_category: [{ category: "head", amount: 30000 }],
      priced_receipt_count: 2, unpriced_receipt_count: 1
    });
    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Открыть/ }));
    expect(await screen.findByText(/Приходов без цены: 1/)).toBeInTheDocument();
  });
});
