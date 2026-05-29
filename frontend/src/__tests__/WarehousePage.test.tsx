import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WarehousePage from "@/pages/warehouse/WarehousePage";

const listLevelsMock = vi.fn();
const listBatchesMock = vi.fn();

vi.mock("@/api/warehouse", () => ({
  warehouseApi: {
    listLevels: (...args: unknown[]) => listLevelsMock(...args),
    listBatches: (...args: unknown[]) => listBatchesMock(...args)
  }
}));

describe("WarehousePage", () => {
  beforeEach(() => {
    listLevelsMock.mockReset();
    listBatchesMock.mockReset();
  });

  it("renders stock levels from the warehouse API", async () => {
    listLevelsMock.mockResolvedValue([
      {
        item_id: "i1",
        item_name: "Каска",
        total_quantity: 12,
        batch_count: 2,
        nearest_certificate_expiry: null
      }
    ]);
    listBatchesMock.mockResolvedValue([
      {
        id: "b1",
        item_id: "i1",
        batch_no: "B-1",
        quantity: 12,
        created_at: "2026-05-29T00:00:00Z",
        updated_at: "2026-05-29T00:00:00Z"
      }
    ]);

    render(
      <MemoryRouter>
        <WarehousePage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Каска")).toBeInTheDocument());
    expect(screen.getByText("Партий: 1")).toBeInTheDocument();
  });

  it("shows an empty state when there are no levels", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <WarehousePage />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText("Позиции не найдены")).toBeInTheDocument());
  });
});
