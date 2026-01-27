import { beforeEach, describe, expect, it } from "vitest";

import { TENANT_OPTIONS } from "@/config/tenants";
import { tenantStorage } from "@/api/tenantStorage";
import { useTenantStore } from "@/stores/tenant";

describe("tenant store", () => {
  beforeEach(() => {
    tenantStorage.clear();
    useTenantStore.getState().clearTenant();
  });

  it("switches tenant and persists selection", () => {
    const { setTenant } = useTenantStore.getState();

    setTenant(TENANT_OPTIONS[0]);
    expect(tenantStorage.getTenant()?.slug).toBe(TENANT_OPTIONS[0].slug);

    setTenant(TENANT_OPTIONS[1]);
    expect(tenantStorage.getTenant()?.slug).toBe(TENANT_OPTIONS[1].slug);
  });
});
