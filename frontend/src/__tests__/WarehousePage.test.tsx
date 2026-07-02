import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WarehousePage from "@/pages/warehouse/WarehousePage";

const listLevelsMock = vi.fn();
const listBatchesMock = vi.fn();
const listMovementsMock = vi.fn();
const createMovementMock = vi.fn();

vi.mock("@/api/warehouse", () => ({
  warehouseApi: {
    listLevels: (...args: unknown[]) => listLevelsMock(...args),
    listBatches: (...args: unknown[]) => listBatchesMock(...args),
    listMovements: (...args: unknown[]) => listMovementsMock(...args),
    createMovement: (...args: unknown[]) => createMovementMock(...args)
  }
}));

describe("WarehousePage", () => {
  beforeEach(() => {
    listLevelsMock.mockReset();
    listBatchesMock.mockReset();
    listMovementsMock.mockReset();
    createMovementMock.mockReset();
    listMovementsMock.mockResolvedValue([]);
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
});
