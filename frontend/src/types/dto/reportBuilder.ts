export type ReportColumnKind = "string" | "number" | "date" | "datetime" | "enum" | "bool";
export type ReportFilterOp = "eq" | "neq" | "contains" | "gte" | "lte" | "in";
export type ReportExportFormat = "csv" | "xlsx" | "pdf";

export interface ReportColumnMetaDto {
  key: string;
  label: string;
  kind: ReportColumnKind;
  aggregatable: boolean;
  enum_values: string[] | null;
  ops: ReportFilterOp[];
}

export interface ReportDatasetDto {
  code: string;
  title: string;
  columns: ReportColumnMetaDto[];
}

export interface ReportFilterDto {
  field: string;
  op: ReportFilterOp;
  value: unknown;
}

export interface ReportSortDto {
  field: string;
  dir: "asc" | "desc";
}

export interface ReportAggregateDto {
  fn: "count" | "sum";
  field?: string;
}

export interface ReportConfigDto {
  columns?: string[];
  filters?: ReportFilterDto[];
  sort?: ReportSortDto[];
  group_by?: string[];
  aggregates?: ReportAggregateDto[];
}

export interface ReportDefinitionDto {
  id: string;
  name: string;
  description: string | null;
  dataset_code: string;
  config_json: ReportConfigDto;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReportPreviewDto {
  columns: { key: string; label: string; kind: string }[];
  rows: Record<string, unknown>[];
  total: number;
}

export interface ReportExportJobDto {
  id: string;
  status: string; // queued | running | done | failed
  file_id: string | null;
  row_count: number | null;
  error_payload: { code?: string; message?: string } | null;
}
