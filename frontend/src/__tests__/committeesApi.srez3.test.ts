import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...a: unknown[]) => getMock(...a),
  },
}));

import { committeesApi, type CommitteeKpi } from "@/api/committees";

beforeEach(() => {
  getMock.mockReset().mockResolvedValue({ data: {} });
});

const sampleKpi: CommitteeKpi = {
  committees_total: 2,
  committees_active: 1,
  meetings_planned: 1,
  meetings_held: 3,
  meetings_cancelled: 0,
  decisions_total: 4,
  tasks_total: 5,
  tasks_open: 2,
  tasks_overdue: 1,
  tasks_done: 3,
  held_meetings: 3,
  avg_attendance_pct: 62.5,
  quorum_rate_pct: 66.7,
};

describe("committeesApi срез-3 (KPI)", () => {
  it("getKpi requests /committees/kpi with empty params by default", async () => {
    getMock.mockResolvedValue({ data: sampleKpi });

    const result = await committeesApi.getKpi();

    expect(getMock).toHaveBeenCalledWith("/committees/kpi", { params: {} });
    expect(result).toEqual(sampleKpi);
  });

  it("getKpi forwards committee_id filter", async () => {
    getMock.mockResolvedValue({ data: sampleKpi });

    await committeesApi.getKpi({ committee_id: "c1" });

    expect(getMock).toHaveBeenCalledWith("/committees/kpi", {
      params: { committee_id: "c1" },
    });
  });
});
