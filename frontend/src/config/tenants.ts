export type TenantOption = {
  id: string;
  slug: string;
  name: string;
  site?: string | null;
};

// Only real, provisioned tenants belong here — the login field offers these as
// autocomplete hints and any slug missing from the database makes every request fail
// with TENANT_INVALID. New tenants are created in /admin/tenants; their admins type
// their own slug (the field is free-form), so we do not hardcode fictional companies.
export const TENANT_OPTIONS: TenantOption[] = [
  { id: "demo", slug: "demo", name: "Demo tenant", site: "Локальная среда" },
];
