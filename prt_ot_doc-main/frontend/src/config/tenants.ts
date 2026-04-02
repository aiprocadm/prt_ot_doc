export type TenantOption = {
  id: string;
  slug: string;
  name: string;
  site?: string | null;
};

export const TENANT_OPTIONS: TenantOption[] = [
  { id: "demo", slug: "demo", name: "Demo tenant", site: "Локальная среда" },
  { id: "1", slug: "severstroy", name: "АО «СеверСтрой»", site: "Северный кластер" },
  { id: "2", slug: "ural", name: "Филиал «Урал»", site: "Площадка Екатеринбург" },
  { id: "3", slug: "promengineering", name: "Подрядчик «ПромИнжиниринг»", site: "Объект 45" }
];
