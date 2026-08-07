import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { clientQuorum, committeesApi } from "@/api/committees";
import { tenantStorage } from "@/api/tenantStorage";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

describe("committeesApi срез-4", () => {
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

  it("putInvitations шлёт person_ids на канонический путь", async () => {
    mock.onPut("/committees/meetings/m1/invitations").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({
        person_ids: ["p1", "p2"],
      });
      return [
        200,
        [
          {
            id: "i1",
            meeting_id: "m1",
            person_id: "p1",
            invited_at: "2026-08-03T10:00:00Z",
          },
        ],
      ];
    });
    const out = await committeesApi.putInvitations("m1", ["p1", "p2"]);
    expect(out).toHaveLength(1);
  });

  it("getInvitations читает канонический путь", async () => {
    mock.onGet("/committees/meetings/m1/invitations").reply(200, []);
    await expect(committeesApi.getInvitations("m1")).resolves.toEqual([]);
  });

  it("createCommittee передаёт порог кворума", async () => {
    mock.onPost("/committees").reply((config) => {
      expect(JSON.parse(config.data as string).quorum_threshold_pct).toBe(66);
      return [201, { id: "c1", kind: "osms", name: "К", is_active: true }];
    });
    await committeesApi.createCommittee({
      kind: "osms",
      name: "К",
      quorum_threshold_pct: 66,
    });
  });

  it("downloadProtocolPrint качает blob с параметром format", async () => {
    mock.onGet("/committees/meetings/m1/protocol/print").reply((config) => {
      expect(config.params?.format).toBe("pdf");
      return [200, new Blob(["pdf-bytes"])];
    });
    const createObjectURL = vi.fn().mockReturnValue("blob:x");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    await committeesApi.downloadProtocolPrint("m1", "pdf", "3-2026");
    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    click.mockRestore();
    vi.unstubAllGlobals();
  });
});

describe("clientQuorum (зеркало серверного правила)", () => {
  it("без порога — строго больше половины", () => {
    expect(clientQuorum(3, 4)).toBe(true);
    expect(clientQuorum(2, 4)).toBe(false);
    expect(clientQuorum(0, 0)).toBe(false);
  });

  it("порог включительно", () => {
    expect(clientQuorum(2, 4, 50)).toBe(true);
    expect(clientQuorum(2, 4, 66)).toBe(false);
    expect(clientQuorum(4, 4, 100)).toBe(true);
  });
});
