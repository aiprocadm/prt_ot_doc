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
  supplier_id?: string | null;
  unit_cost?: number | null;
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

export type StockTransferDto = {
  ref_id: string;
  item_id: string;
  item_name: string;
  batch_no: string;
  from_location?: string | null;
  to_location: string;
  quantity: number;
  source_batch_id: string;
  dest_batch_id: string;
  out_movement_id: string;
  in_movement_id: string;
  reason?: string | null;
  occurred_at: string;
};

export type CreateTransferInput = {
  source_batch_id: string;
  to_location: string;
  quantity: number;
  reason?: string | null;
};

export type StockLevelByLocationDto = {
  item_id: string;
  item_name: string;
  location?: string | null;
  quantity: number;
  batch_count: number;
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
  supplier_id: string | null;
  supplier_name: string | null;
  supplier_inn: string | null;
  supplier_contact: string | null;
  supplier_source: "explicit" | "history" | null;
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

export type InventoryCountLineEntry = {
  line_id: string;
  counted_qty: number | null;
};

export type SupplierDto = {
  id: string;
  name: string;
  inn?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
};

export type SupplierInput = {
  name: string;
  inn?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
};

export type ReorderLineDto = {
  item_id: string;
  item_name: string;
  deficit: number;
};

export type ReorderGroupDto = {
  supplier_id: string | null;
  supplier_name: string | null;
  supplier_inn: string | null;
  supplier_contact: string | null;
  lines: ReorderLineDto[];
  line_count: number;
  total_deficit: number;
};

export type ReorderDraftDto = {
  groups: ReorderGroupDto[];
  total_lines: number;
  total_deficit: number;
};

export type BudgetDto = {
  id: string;
  name: string;
  period_start: string;
  period_end: string;
  planned_amount: number;
  notes?: string | null;
  created_at: string;
  updated_at: string;
};

export type BudgetCategoryActualDto = { category: string; amount: number };

export type BudgetDetailDto = BudgetDto & {
  actual_total: number;
  remaining: number;
  by_category: BudgetCategoryActualDto[];
  priced_receipt_count: number;
  unpriced_receipt_count: number;
};

export type BudgetCreateInput = {
  name: string;
  period_start: string;
  period_end: string;
  planned_amount: number;
  notes?: string | null;
};

export type CreateBatchInput = {
  item_id: string;
  batch_no: string;
  quantity?: number;
  location?: string | null;
  received_at?: string | null;
  certificate_no?: string | null;
  certificate_expires_at?: string | null;
  supplier_id?: string | null;
  unit_cost?: number | null;
};

type PageResponse<T> = { items: T[]; total: number };
type ShortagePageResponse = {
  items: PPEStockShortageDto[];
  total: number;
  window_days: number;
};

export const warehouseApi = {
  async listBatches(): Promise<StockBatchDto[]> {
    const response = await apiClient.get<PageResponse<StockBatchDto>>(
      "/ppe/stock/batches",
      {
        params: { limit: 100, offset: 0 },
      },
    );
    return response.data.items ?? [];
  },
  async listLevels(): Promise<StockLevelDto[]> {
    const response =
      await apiClient.get<PageResponse<StockLevelDto>>("/ppe/stock/levels");
    return response.data.items ?? [];
  },
  async listMovements(): Promise<StockMovementDto[]> {
    const response = await apiClient.get<PageResponse<StockMovementDto>>(
      "/ppe/stock/movements",
      {
        params: { limit: 50, offset: 0 },
      },
    );
    return response.data.items ?? [];
  },
  async createMovement(input: CreateMovementInput): Promise<StockMovementDto> {
    const response = await apiClient.post<StockMovementDto>(
      "/ppe/stock/movements",
      input,
    );
    return response.data;
  },
  async listTransfers(params?: {
    item_id?: string;
  }): Promise<StockTransferDto[]> {
    const response = await apiClient.get<PageResponse<StockTransferDto>>(
      "/ppe/stock/transfers",
      {
        params: { limit: 50, offset: 0, ...(params ?? {}) },
      },
    );
    return response.data.items ?? [];
  },
  async createTransfer(input: CreateTransferInput): Promise<StockTransferDto> {
    const response = await apiClient.post<StockTransferDto>(
      "/ppe/stock/transfers",
      input,
    );
    return response.data;
  },
  async listLevelsByLocation(): Promise<StockLevelByLocationDto[]> {
    const response = await apiClient.get<PageResponse<StockLevelByLocationDto>>(
      "/ppe/stock/levels/by-location",
    );
    return response.data.items ?? [];
  },
  async listShortages(params?: {
    window_days?: number;
    only_below?: boolean;
  }): Promise<PPEStockShortageDto[]> {
    const response = await apiClient.get<ShortagePageResponse>(
      "/ppe/stock/shortages",
      { params },
    );
    return response.data.items ?? [];
  },
  async listCounts(): Promise<InventoryCountDto[]> {
    const response = await apiClient.get<PageResponse<InventoryCountDto>>(
      "/ppe/stock/inventory/counts",
      { params: { limit: 50, offset: 0 } },
    );
    return response.data.items ?? [];
  },
  async createCount(
    input: CreateInventoryCountInput,
  ): Promise<InventoryCountDetailDto> {
    const response = await apiClient.post<InventoryCountDetailDto>(
      "/ppe/stock/inventory/counts",
      input,
    );
    return response.data;
  },
  async getCount(id: string): Promise<InventoryCountDetailDto> {
    const response = await apiClient.get<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}`,
    );
    return response.data;
  },
  async patchCountLines(
    id: string,
    entries: InventoryCountLineEntry[],
  ): Promise<InventoryCountDetailDto> {
    const response = await apiClient.patch<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}/lines`,
      { entries },
    );
    return response.data;
  },
  async applyCount(id: string): Promise<InventoryCountDetailDto> {
    const response = await apiClient.post<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}/apply`,
      {},
    );
    return response.data;
  },
  async cancelCount(id: string): Promise<InventoryCountDetailDto> {
    const response = await apiClient.post<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}/cancel`,
      {},
    );
    return response.data;
  },
  async createBatch(input: CreateBatchInput): Promise<StockBatchDto> {
    const response = await apiClient.post<StockBatchDto>(
      "/ppe/stock/batches",
      input,
    );
    return response.data;
  },
  async listSuppliers(): Promise<SupplierDto[]> {
    const response = await apiClient.get<PageResponse<SupplierDto>>(
      "/ppe/suppliers",
      {
        params: { limit: 200, offset: 0 },
      },
    );
    return response.data.items ?? [];
  },
  async createSupplier(input: SupplierInput): Promise<SupplierDto> {
    const response = await apiClient.post<SupplierDto>("/ppe/suppliers", input);
    return response.data;
  },
  async updateSupplier(
    id: string,
    input: Partial<SupplierInput>,
  ): Promise<SupplierDto> {
    const response = await apiClient.patch<SupplierDto>(
      `/ppe/suppliers/${id}`,
      input,
    );
    return response.data;
  },
  async deleteSupplier(id: string): Promise<void> {
    await apiClient.delete(`/ppe/suppliers/${id}`);
  },
  async getReorderDraft(params?: {
    window_days?: number;
  }): Promise<ReorderDraftDto> {
    const response = await apiClient.get<ReorderDraftDto>(
      "/ppe/stock/reorder",
      { params },
    );
    return response.data;
  },
  async patchItemPreferredSupplier(
    itemId: string,
    supplierId: string | null,
  ): Promise<void> {
    await apiClient.patch(`/ppe/items/${itemId}`, {
      preferred_supplier_id: supplierId,
    });
  },
  async listBudgets(): Promise<BudgetDto[]> {
    const response = await apiClient.get<PageResponse<BudgetDto>>(
      "/ppe/budgets",
      {
        params: { limit: 100, offset: 0 },
      },
    );
    return response.data.items ?? [];
  },
  async getBudget(id: string): Promise<BudgetDetailDto> {
    const response = await apiClient.get<BudgetDetailDto>(`/ppe/budgets/${id}`);
    return response.data;
  },
  async createBudget(input: BudgetCreateInput): Promise<BudgetDto> {
    const response = await apiClient.post<BudgetDto>("/ppe/budgets", input);
    return response.data;
  },
  async updateBudget(
    id: string,
    input: Partial<BudgetCreateInput>,
  ): Promise<BudgetDto> {
    const response = await apiClient.patch<BudgetDto>(
      `/ppe/budgets/${id}`,
      input,
    );
    return response.data;
  },
  async deleteBudget(id: string): Promise<void> {
    await apiClient.delete(`/ppe/budgets/${id}`);
  },
};
