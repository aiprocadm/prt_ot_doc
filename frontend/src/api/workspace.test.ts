import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { tenantStorage } from "@/api/tenantStorage";
import { workspaceApi } from "@/api/workspace";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

describe("workspaceApi.getUserWorkspaceConfig", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    tenantStorage.setTenant({ slug: "severstroy", site: "Северный кластер" });
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
    tenantStorage.clear();
    vi.clearAllMocks();
  });

  it("запрашивает конфиг по каноничному пути /workspace/users/me/workspace", async () => {
    const config = {
      role: "admin",
      workspace_type: "admin",
      primary_modules: ["dashboard"],
      dashboard_route: "/dashboard",
      kpis_enabled: [],
      quick_actions: [],
    };
    mock.onGet("/workspace/users/me/workspace").reply(200, config);

    await expect(workspaceApi.getUserWorkspaceConfig()).resolves.toMatchObject({
      dashboard_route: "/dashboard",
      role: "admin",
    });
  });
});
