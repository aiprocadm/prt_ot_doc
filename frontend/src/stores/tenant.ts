import { create } from "zustand";

import { tenantStorage, type StoredTenant } from "@/api/tenantStorage";
import { TENANT_OPTIONS, type TenantOption } from "@/config/tenants";
import { resetTenantStores } from "@/stores/reset";

type TenantInput = {
  slug: string;
  site?: string | null;
  name?: string;
  id?: string;
};

interface TenantState {
  tenant: TenantOption | null;
  tenants: TenantOption[];
  setTenant: (tenant: TenantInput) => void;
  clearTenant: () => void;
}

const resolveTenant = (stored: StoredTenant | null): TenantOption | null => {
  if (!stored) return null;
  const match = TENANT_OPTIONS.find((option) => option.slug === stored.slug);
  if (match) return match;
  return {
    id: stored.slug,
    slug: stored.slug,
    name: stored.slug,
    site: stored.site ?? null,
  };
};

const normalizeTenant = (tenant: TenantInput): TenantOption => {
  const match = TENANT_OPTIONS.find((option) => option.slug === tenant.slug);
  if (match) return match;
  return {
    id: tenant.id ?? tenant.slug,
    slug: tenant.slug,
    name: tenant.name?.trim() || tenant.slug,
    site: tenant.site ?? null,
  };
};

export const useTenantStore = create<TenantState>((set) => ({
  tenant: resolveTenant(tenantStorage.getTenant()),
  tenants: [...TENANT_OPTIONS],
  setTenant: (tenant) => {
    const nextTenant = normalizeTenant(tenant);
    tenantStorage.setTenant({ slug: nextTenant.slug, site: nextTenant.site });
    resetTenantStores();
    set({ tenant: nextTenant });
  },
  clearTenant: () => {
    tenantStorage.clear();
    resetTenantStores();
    set({ tenant: null });
  },
}));
