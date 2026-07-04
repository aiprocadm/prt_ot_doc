import { apiClient } from "@/api/client";

export type StockBatchDto = {
  id: string;
  item_id: string;
  batch_no: string;
  quantity: number;
  received_at?: string | null;
  certificate_no?: string | null;
  certificate_expires_at?: string | null;
  location?: string | null;
  created_at: string;
  updated_at: string;
};

export type StockLevelDto = {
  item_id: string;
  item_name: string;
  total_quantity: number;
  batch_count: number;
  nearest_certificate_expiry?: string | null;
};

export type StockMovementDto = {
  id: string;
  item_id: string;
  batch_id: string | null;
  kind: "receipt" | "issue" | "writeoff" | "adjustment";
  quantity_delta: number;
  occurred_at: string;
  reason?: string | null;
  ref_type?: string | null;
  ref_id?: string | null;
  created_at: string;
};

export type CreateMovementInput = {
  batch_id: string;
  kind: "receipt" | "writeoff" | "adjustment";
  quantity: number;
  reason?: string | null;
};

export type PPEStockShortageDto = {
  item_id: string;
  item_name: string;
  min_stock: number;
  on_hand: number;
  deficit: number;
  below_threshold: boolean;
  avg_daily_consumption: number;
  days_to_depletion: number | null;
  projected_breach_date: string | null;
};

export type InventoryCountStatus = "draft" | "applied" | "cancelled";

export type InventoryCountLineDto = {
  id: string;
  batch_id: string;
  item_id: string;
  batch_no: string;
  location?: string | null;
  item_name: string;
  system_qty: number;
  counted_qty: number | null;
  on_hand: number;
  delta: number | null;
  adjustment_movement_id?: string | null;
};

export type InventoryCountDto = {
  id: string;
  status: InventoryCountStatus;
  scope_item_id?: string | null;
  scope_location?: string | null;
  note?: string | null;
  applied_at?: string | null;
  created_at: string;
  line_count: number;
  counted_count: number;
};

export type InventoryCountDetailDto = InventoryCountDto & {
  diff_count: number;
  lines: InventoryCountLineDto[];
};

export type CreateInventoryCountInput = {
  scope_item_id?: string | null;
  scope_location?: string | null;
  note?: string | null;
};

export type InventoryCountLineEntry = { line_id: string; counted_qty: number | null };

type PageResponse<T> = { items: T[]; total: number };
type ShortagePageResponse = { items: PPEStockShortageDto[]; total: number; window_days: number };

export const warehouseApi = {
  async listBatches(): Promise<StockBatchDto[]> {
    const response = await apiClient.get<PageResponse<StockBatchDto>>("/ppe/stock/batches", {
      params: { limit: 100, offset: 0 }
    });
    return response.data.items ?? [];
  },
  async listLevels(): Promise<StockLevelDto[]> {
    const response = await apiClient.get<PageResponse<StockLevelDto>>("/ppe/stock/levels");
    return response.data.items ?? [];
  },
  async listMovements(): Promise<StockMovementDto[]> {
    const response = await apiClient.get<PageResponse<StockMovementDto>>("/ppe/stock/movements", {
      params: { limit: 50, offset: 0 }
    });
    return response.data.items ?? [];
  },
  async createMovement(input: CreateMovementInput): Promise<StockMovementDto> {
    const response = await apiClient.post<StockMovementDto>("/ppe/stock/movements", input);
    return response.data;
  },
  async listShortages(params?: { window_days?: number; only_below?: boolean }): Promise<PPEStockShortageDto[]> {
    const response = await apiClient.get<ShortagePageResponse>("/ppe/stock/shortages", { params });
    return response.data.items ?? [];
  },
  async listCounts(): Promise<InventoryCountDto[]> {
    const response = await apiClient.get<PageResponse<InventoryCountDto>>(
      "/ppe/stock/inventory/counts",
      { params: { limit: 50, offset: 0 } }
    );
    return response.data.items ?? [];
  },
  async createCount(input: CreateInventoryCountInput): Promise<InventoryCountDetailDto> {
    const response = await apiClient.post<InventoryCountDetailDto>(
      "/ppe/stock/inventory/counts",
      input
    );
    return response.data;
  },
  async getCount(id: string): Promise<InventoryCountDetailDto> {
    const response = await apiClient.get<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}`
    );
    return response.data;
  },
  async patchCountLines(
    id: string,
    entries: InventoryCountLineEntry[]
  ): Promise<InventoryCountDetailDto> {
    const response = await apiClient.patch<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}/lines`,
      { entries }
    );
    return response.data;
  },
  async applyCount(id: string): Promise<InventoryCountDetailDto> {
    const response = await apiClient.post<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}/apply`,
      {}
    );
    return response.data;
  },
  async cancelCount(id: string): Promise<InventoryCountDetailDto> {
    const response = await apiClient.post<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}/cancel`,
      {}
    );
    return response.data;
  }
};
