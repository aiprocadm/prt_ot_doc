// OPS-71 (разд. 71.1): контракты импорт-фреймворка.
// Зеркало `backend/app/modules/imports/api.py`.

export type ImportColumnKind = "str" | "int" | "date" | "enum" | "bool";

export interface ImportColumnDto {
  field: string;
  title: string;
  kind: ImportColumnKind;
  required: boolean;
  aliases: string[];
  enum_values: string[];
  lookup: string | null;
  /** Можно ли дозавести недостающую запись этого справочника прямо из импорта. */
  lookup_creatable: boolean;
}

export interface ImportTargetDto {
  code: string;
  title: string;
  description: string;
  natural_keys: string[];
  columns: ImportColumnDto[];
}

export type ImportRowAction = "create" | "update" | "skip" | "error";

export interface ImportRowErrorDto {
  code: string;
  field: string | null;
  message: string;
}

export interface ImportPlannedRowDto {
  row_number: number;
  action: ImportRowAction;
  natural_key: string | null;
  changed_fields: string[];
  errors: ImportRowErrorDto[];
}

export interface ImportProfileDto {
  code: string;
  title: string;
  target: string;
  source: string;
  description: string;
  mapping: Record<string, string>;
  split_columns: string[];
}

export interface ImportPreviewDto {
  target: string;
  /** Профиль, опознанный по заголовкам файла: подсказка, а не решение. */
  detected_profile: string | null;
  applied_profile: string | null;
  counts: Record<string, number>;
  mapping: Record<string, string>;
  unmapped_headers: string[];
  unknown_references: Record<string, string[]>;
  rows: ImportPlannedRowDto[];
}

export type ImportBatchStatus =
  | "pending"
  | "running"
  | "applied"
  | "previewed"
  | "failed"
  | "rolled_back";

/** `preview` — фоновый сухой прогон: план посчитан, в целевые таблицы не писали. */
export type ImportBatchMode = "apply" | "preview";

export interface ImportBatchDto {
  id: string;
  target: string;
  status: ImportBatchStatus;
  mode: ImportBatchMode;
  source_filename: string;
  source_format: string;
  mapping: Record<string, string>;
  notes: Record<string, unknown>;
  total_rows: number;
  /** Сколько строк уже обработано фоновой загрузкой (срез-2 бэкенда). */
  processed_rows: number;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  failed_count: number;
  applied_at: string;
  applied_by: string | null;
  finished_at: string | null;
  /** Причина обрыва фоновой загрузки: «failed» без причины отправляет читать логи. */
  error_message: string | null;
  rolled_back_at: string | null;
  rolled_back_by: string | null;
}

export interface ImportBatchRowDto {
  row_number: number;
  action: "created" | "updated" | "skipped" | "failed";
  natural_key: string | null;
  entity_id: string | null;
  errors: Array<Record<string, unknown>>;
  message: string | null;
}

export interface ImportApplyDto {
  batch: ImportBatchDto;
  preview: ImportPreviewDto;
}
