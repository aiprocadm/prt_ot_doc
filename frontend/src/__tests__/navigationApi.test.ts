import MockAdapter from "axios-mock-adapter";
import { describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { getTopNavKpi } from "@/api/navigation";
import { tenantStorage } from "@/api/tenantStorage";

describe("navigation api", () => {
  it("loads top nav KPI counters", async () => {
    tenantStorage.setTenant({ slug: "demo" });
    const mock = new MockAdapter(apiClient);
    mock.onGet("/workflow/tasks").reply(200, [{ id: "1" }, { id: "2" }]);
    mock.onGet("/notifications").reply(200, { unread_count: 4 });

    await expect(getTopNavKpi()).resolves.toEqual({ tasks: 2, alerts: 4 });

    mock.restore();
  });
});

