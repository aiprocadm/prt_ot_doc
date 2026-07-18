import type { BaseEntityDto } from "./common";

export type NpaStatus = "active" | "obsolete" | "draft";

export interface NpaDto extends BaseEntityDto {
  title: string;
  code?: string;
  issuer?: string;
  published_at?: string;
  effective_at?: string;
  status: NpaStatus;
  link?: string;
  tags?: string[];
}

export interface NpaFiltersDto {
  search?: string;
  status?: NpaStatus;
  issuer?: string;
  year?: number;
}
