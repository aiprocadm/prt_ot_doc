export type DocumentStage =
  | "validate_template"
  | "render_docx"
  | "apply_headers"
  | "replace"
  | "quality_gate"
  | "convert_pdf"
  | "send_for_approval"
  | "sign"
  | "send_edo"
  | "archive";

export type DocumentIssueSeverity = "critical" | "warning";

export type QualityIssue = {
  code: string;
  message: string;
  severity: DocumentIssueSeverity;
  stage: DocumentStage;
  details: Record<string, unknown>;
};

export type QualityReport = {
  status: "passed" | "failed";
  release_blocked: boolean;
  summary: Record<string, number>;
  issues: QualityIssue[];
};
