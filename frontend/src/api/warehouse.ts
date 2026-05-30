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
  }
};
