import { describe, it, expect, vi, beforeEach } from "vitest";

import { apiClient } from "@/api/client";
import { isFeatureDisabledError, rulesApi } from "@/api/rules";
import type { AutomationRuleCreate, DryRunIn } from "@/types/dto/rules";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  (apiClient.get as any).mockResolvedValue({ data: { items: [], total: 0 } });
  (apiClient.post as any).mockResolvedValue({ data: { id: "x" } });
  (apiClient.patch as any).mockResolvedValue({ data: { id: "x" } });
  (apiClient.delete as any).mockResolvedValue({ data: null });
});

describe("rulesApi", () => {
  it("lists rules with default paging", async () => {
    await rulesApi.list();
    expect(apiClient.get).toHaveBeenCalledWith("/rules", {
      params: { limit: 100, offset: 0 },
    });
  });

  it("merges paging overrides into list()", async () => {
    await rulesApi.list({ limit: 20, offset: 40 });
    expect(apiClient.get).toHaveBeenCalledWith("/rules", {
      params: { limit: 20, offset: 40 },
    });
  });

  it("creates a rule by posting the body to /rules", async () => {
    const payload: AutomationRuleCreate = {
      name: "Rule",
      event_type: "IncidentCreated",
      conditions_json: {},
      actions_json: [],
      priority: 100,
      is_enabled: true,
    };
    (apiClient.post as any).mockResolvedValue({
      data: { ...payload, id: "r1", created_at: "now", updated_at: "now" },
    });
    const created = await rulesApi.create(payload);
    expect(apiClient.post).toHaveBeenCalledWith("/rules", payload);
    expect(created.id).toBe("r1");
  });

  it("dry-runs a rule against /rules/dry-run", async () => {
    const payload: DryRunIn = {
      rule: {
        name: "Rule",
        event_type: "IncidentCreated",
        conditions_json: {},
        actions_json: [],
        priority: 100,
        is_enabled: true,
      },
      event: { event_type: "IncidentCreated", payload: {} },
    };
    await rulesApi.dryRun(payload);
    expect(apiClient.post).toHaveBeenCalledWith("/rules/dry-run", payload);
  });

  it("lists triggers scoped by rule_id with default paging", async () => {
    await rulesApi.triggers({ rule_id: "r1" });
    expect(apiClient.get).toHaveBeenCalledWith("/rules/triggers", {
      params: { rule_id: "r1", limit: 50, offset: 0 },
    });
  });

  it("detects the feature-disabled 404", () => {
    expect(
      isFeatureDisabledError({
        status: 404,
        message: "Rules engine feature is not enabled for this tenant",
      }),
    ).toBe(true);
    expect(isFeatureDisabledError({ status: 404, message: "Not found" })).toBe(
      false,
    );
    expect(
      isFeatureDisabledError({
        status: 403,
        message: "feature is not enabled",
      }),
    ).toBe(false);
    expect(isFeatureDisabledError(undefined)).toBe(false);
  });
});
