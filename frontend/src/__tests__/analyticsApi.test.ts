import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: { get: (...args: unknown[]) => getMock(...args) },
}));

import { analyticsApi } from "@/api/analyticsApi";

describe("analyticsApi", () => {
  beforeEach(() => {
    getMock.mockReset().mockResolvedValue({ data: {} });
  });

  it("fetches dashboards with filters as params (undefined omitted)", async () => {
    await analyticsApi.getDashboard("overdue", {
      company_id: "c1",
      date_from: "2026-07-01",
    });
    expect(getMock).toHaveBeenCalledWith("/analytics/dashboard/overdue", {
      params: { company_id: "c1", date_from: "2026-07-01" },
    });
    await analyticsApi.getDashboard("executive", {});
    expect(getMock).toHaveBeenLastCalledWith("/analytics/dashboard/executive", {
      params: {},
    });
  });

  it("fetches trends with period (no filters — endpoint is tenant-wide)", async () => {
    await analyticsApi.getTrend("incidents", "weekly");
    expect(getMock).toHaveBeenCalledWith("/analytics/trends/incidents", {
      params: { period: "weekly" },
    });
  });

  it("fetches breakdown with dimension and window", async () => {
    await analyticsApi.getBreakdown("site", { date_from: "2026-07-01" });
    expect(getMock).toHaveBeenCalledWith("/analytics/dashboard/breakdown", {
      params: { dimension: "site", date_from: "2026-07-01" },
    });
  });

  it("fetches filter directories", async () => {
    await analyticsApi.getCompanies();
    expect(getMock).toHaveBeenCalledWith("/companies", {
      params: { limit: 200 },
    });
    await analyticsApi.getSites();
    expect(getMock).toHaveBeenCalledWith("/sites", { params: { limit: 200 } });
    await analyticsApi.getContractors();
    expect(getMock).toHaveBeenCalledWith("/contractors/registry", {
      params: { limit: 200 },
    });
  });
});
