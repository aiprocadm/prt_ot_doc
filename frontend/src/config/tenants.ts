export const TENANT_OPTIONS = [
  { id: "1", slug: "severstroy", name: "АО «СеверСтрой»", site: "Северный кластер" },
  { id: "2", slug: "ural", name: "Филиал «Урал»", site: "Площадка Екатеринбург" },
  { id: "3", slug: "promengineering", name: "Подрядчик «ПромИнжиниринг»", site: "Объект 45" }
] as const;

export type TenantOption = (typeof TENANT_OPTIONS)[number];
