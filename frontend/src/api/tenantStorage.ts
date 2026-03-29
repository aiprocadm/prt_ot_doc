import { localStorageGetItem, localStorageRemoveItem, localStorageSetItem } from "@/utils/browserStorage";

const TENANT_KEY = "prt-tenant";

export type StoredTenant = {
  slug: string;
  site?: string | null;
};

let tenantValue: StoredTenant | null = null;

const parseTenant = (raw: string | null): StoredTenant | null => {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed === "string") {
      return { slug: parsed };
    }
    if (parsed && typeof parsed.slug === "string") {
      return {
        slug: parsed.slug,
        site: typeof parsed.site === "string" ? parsed.site : null
      };
    }
    return null;
  } catch {
    return { slug: raw };
  }
};

const readTenant = () => {
  return parseTenant(localStorageGetItem(TENANT_KEY));
};

const persistTenant = (tenant: StoredTenant | null) => {
  if (tenant) {
    localStorageSetItem(TENANT_KEY, JSON.stringify(tenant));
  } else {
    localStorageRemoveItem(TENANT_KEY);
  }
};

export const tenantStorage = {
  getTenant: () => tenantValue ?? readTenant(),
  setTenant: (tenant: StoredTenant | null) => {
    tenantValue = tenant;
    persistTenant(tenant);
  },
  hydrate: () => {
    tenantValue = readTenant();
  },
  clear: () => {
    tenantValue = null;
    persistTenant(null);
  }
};
