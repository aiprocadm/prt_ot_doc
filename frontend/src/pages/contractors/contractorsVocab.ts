import type {
  AdmissionStatus,
  ComplianceStatus,
  DocScope,
  DocType,
  ExpiryStatus,
  IncidentSeverity,
} from "@/types/dto/contractors";

export const COMPLIANCE_STATUS_LABELS: Record<ComplianceStatus, string> = {
  valid: "Действителен",
  pending: "Ожидает",
  expired: "Просрочен",
  blocked: "Заблокирован",
};

export const COMPLIANCE_STATUS_OPTIONS: ComplianceStatus[] = [
  "pending",
  "valid",
  "expired",
  "blocked",
];

export const SEVERITY_LABELS: Record<IncidentSeverity, string> = {
  low: "Низкая",
  medium: "Средняя",
  high: "Высокая",
  critical: "Критическая",
};

export const SEVERITY_OPTIONS: IncidentSeverity[] = [
  "low",
  "medium",
  "high",
  "critical",
];

export const DOC_TYPE_LABELS: Record<DocType, string> = {
  license: "Лицензия",
  insurance: "Страховка",
  contract: "Договор",
  sro: "СРО",
  training_cert: "Удостоверение об обучении",
  medical_cert: "Медицинское заключение",
  access_permit: "Наряд-допуск",
  qualification: "Квалификация",
  other: "Другое",
};

export const DOC_TYPE_OPTIONS: DocType[] = [
  "license",
  "insurance",
  "contract",
  "sro",
  "training_cert",
  "medical_cert",
  "access_permit",
  "qualification",
  "other",
];

export const SCOPE_LABELS: Record<DocScope, string> = {
  company: "На компанию",
  employee: "На сотрудника",
};

export const SCOPE_OPTIONS: DocScope[] = ["company", "employee"];

export const EXPIRY_LABELS: Record<ExpiryStatus, string> = {
  ok: "Действует",
  due_soon: "Истекает",
  overdue: "Просрочен",
  missing: "Отсутствует",
};

export const EXPIRY_BADGE_VARIANT: Record<
  ExpiryStatus,
  "default" | "secondary" | "destructive"
> = {
  ok: "default",
  due_soon: "secondary",
  overdue: "destructive",
  missing: "secondary",
};

export const ADMISSION_STATUS_LABELS: Record<AdmissionStatus, string> = {
  allowed: "Допущен",
  warning: "Допущен с замечаниями",
  blocked: "Не допущен",
};
