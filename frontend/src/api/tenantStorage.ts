const TENANT_KEY = "prt-tenant";
let tenantSlug: string | null = null;

const readTenant = () => {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TENANT_KEY);
};

const persistTenant = (slug: string | null) => {
  if (typeof window === "undefined") return;
  if (slug) {
    window.localStorage.setItem(TENANT_KEY, slug);
  } else {
    window.localStorage.removeItem(TENANT_KEY);
  }
};

export const tenantStorage = {
  getTenant: () => tenantSlug ?? readTenant(),
  setTenant: (slug: string | null) => {
    tenantSlug = slug;
    persistTenant(slug);
  },
  hydrate: () => {
    tenantSlug = readTenant();
  },
  clear: () => {
    tenantSlug = null;
    persistTenant(null);
  }
};
