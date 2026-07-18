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
