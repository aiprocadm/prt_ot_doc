import type {
  BreakdownDimension,
  BudgetDomain,
  BudgetOverviewDomainCode,
  BudgetReimbursementStatus
} from "@/types/dto/budget";
import type { ApiError } from "@/types/dto/common";

export const BUDGET_DOMAIN_LABELS: Record<BudgetOverviewDomainCode, string> = {
  training: "Обучение",
  medical: "Медосмотры",
  events: "Мероприятия",
  ppe: "СИЗ (склад)"
};

/**
 * Домены, которыми управляет пользователь (без read-only "ppe" — тот ведётся на складе).
 * Один источник для фильтров и селектов всех вкладок бюджета.
 */
export const BUDGET_DOMAINS: BudgetDomain[] = ["training", "medical", "events"];

/** Нормализует неизвестную ошибку до ApiError для локальных ErrorState во вкладках. */
export const toApiError = (err: unknown, fallback: string): ApiError =>
  err && typeof err === "object" && "message" in err ? (err as ApiError) : { status: 0, message: fallback };

export const BREAKDOWN_DIMENSION_LABELS: Record<BreakdownDimension, string> = {
  article: "По статьям",
  domain: "По доменам",
  company: "По компаниям",
  branch: "По филиалам",
  site: "По объектам"
};

const rubFormatter = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0
});

/** Единый формат денег для всех вкладок бюджета (Сводка / Бюджеты / Расходы / Возмещения). */
export const formatRub = (value: number): string => rubFormatter.format(value);

/**
 * Статусы заявок на возмещение СФР — для фильтра вкладки «Возмещения СФР».
 * Подписи бейджей живут в общем StatusBadge (те же ключи), здесь — только порядок FSM.
 */
export const REIMBURSEMENT_STATUSES: BudgetReimbursementStatus[] = [
  "draft",
  "submitted",
  "approved",
  "rejected",
  "paid"
];

export const REIMBURSEMENT_STATUS_LABELS: Record<BudgetReimbursementStatus, string> = {
  draft: "Черновик",
  submitted: "Подана",
  approved: "Одобрена",
  rejected: "Отклонена",
  paid: "Выплачена"
};
