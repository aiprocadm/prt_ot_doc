export interface PaginationDto {
  page: number;
  page_size: number;
  total: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  pagination: PaginationDto;
}

export interface ApiFieldError {
  field: string;
  message: string;
  code?: string;
}

export interface ApiError {
  status: number;
  code?: string;
  type?: string;
  message: string;
  details?: unknown;
  field_errors?: ApiFieldError[];
  correlation_id?: string;
  timestamp?: string;
}

export interface FileLinkDto {
  id: string;
  url: string;
  name: string;
  mime_type: string;
  size: number;
  created_at: string;
}

export interface AuditMetadataDto {
  ip?: string;
  user_agent?: string;
  payload?: Record<string, unknown>;
}

export interface BaseEntityDto {
  id: string;
  created_at: string;
  updated_at: string;
}
