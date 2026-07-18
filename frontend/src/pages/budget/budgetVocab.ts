import type { BreakdownDimension, BudgetOverviewDomainCode } from "@/types/dto/budget";

export const BUDGET_DOMAIN_LABELS: Record<BudgetOverviewDomainCode, string> = {
  training: "Обучение",
  medical: "Медосмотры",
  events: "Мероприятия",
  ppe: "СИЗ (склад)"
};

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

/** Единый формат денег для всех вкладок бюджета (Сводка / Бюджеты / Расходы). */
export const formatRub = (value: number): string => rubFormatter.format(value);
