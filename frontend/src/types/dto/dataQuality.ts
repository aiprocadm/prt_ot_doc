export type DataQualityIssueType =
  | "missing_field"
  | "broken_relationship"
  | "expired_record"
  | "duplicate"
  | "invalid_value"
  | "data_mismatch";

export type DataQualityIssueSeverity = "critical" | "high" | "medium" | "low";

export interface DataQualityIssueDto {
  id: string;
  issue_type: DataQualityIssueType | string;
  severity: DataQualityIssueSeverity | string;
  title: string;
  description?: string | null;
  affected_entity_type: string;
  affected_entity_id: string;
  affected_entity_name?: string | null;
  additional_info?: Record<string, unknown> | null;
  found_at: string;
}

export interface DataQualityCheckResultDto {
  rule_name: string;
  rule_description: string;
  total_checked: number;
  issues_found: number;
  issues: DataQualityIssueDto[];
  execution_time_ms: number;
}

export interface DataQualityReportDto {
  tenant_id: string;
  completeness_percent: number;
  total_issues: number;
  critical_issues: number;
  high_issues: number;
  medium_issues: number;
  low_issues: number;
  issue_breakdown: Record<string, number>;
  entity_breakdown: Record<string, number>;
  issues: DataQualityIssueDto[];
  check_results: DataQualityCheckResultDto[];
  generated_at: string;
}
