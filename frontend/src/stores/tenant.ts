import { create } from "zustand";

import { tenantStorage, type StoredTenant } from "@/api/tenantStorage";
import { TENANT_OPTIONS, type TenantOption } from "@/config/tenants";
import { resetTenantStores } from "@/stores/reset";

interface TenantState {
  tenant: TenantOption | null;
  tenants: TenantOption[];
  setTenant: (tenant: TenantOption) => void;
  clearTenant: () => void;
}

const resolveTenant = (stored: StoredTenant | null): TenantOption | null => {
  if (!stored) return null;
  const match = TENANT_OPTIONS.find((option) => option.slug === stored.slug);
  return match ?? null;
};

export const useTenantStore = create<TenantState>((set) => ({
  tenant: resolveTenant(tenantStorage.getTenant()),
  tenants: [...TENANT_OPTIONS],
  setTenant: (tenant) => {
    tenantStorage.setTenant({ slug: tenant.slug, site: tenant.site });
    resetTenantStores();
    set({ tenant });
  },
  clearTenant: () => {
    tenantStorage.clear();
    resetTenantStores();
    set({ tenant: null });
  }
}));
