import { beforeEach, describe, expect, it } from "vitest";

import { TENANT_OPTIONS } from "@/config/tenants";
import { tenantStorage } from "@/api/tenantStorage";
import { useDocumentsWizardStore } from "@/stores/documentsWizard";
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

  it("resets documents wizard state when tenant changes", () => {
    const { setTenant } = useTenantStore.getState();
    useDocumentsWizardStore.setState({
      companyId: "company-old",
      siteId: "site-old",
      templateCode: "template-old",
      step: 6
    });

    setTenant(TENANT_OPTIONS[0]);

    const wizardState = useDocumentsWizardStore.getState();
    expect(wizardState.companyId).toBe("");
    expect(wizardState.siteId).toBe("");
    expect(wizardState.templateCode).toBe("");
    expect(wizardState.step).toBe(1);
  });

  it("resets documents wizard state on clearTenant", () => {
    useDocumentsWizardStore.setState({
      companyId: "company-old",
      taskId: "task-old",
      step: 7
    });

    useTenantStore.getState().clearTenant();

    const wizardState = useDocumentsWizardStore.getState();
    expect(wizardState.companyId).toBe("");
    expect(wizardState.taskId).toBe("");
    expect(wizardState.step).toBe(1);
  });
});
