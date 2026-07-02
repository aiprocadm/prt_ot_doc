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

type PageResponse<T> = { items: T[]; total: number };

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
  }
};
