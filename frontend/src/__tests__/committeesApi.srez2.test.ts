import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
const postMock = vi.fn();
const putMock = vi.fn();
const patchMock = vi.fn();
const deleteMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    put: (...a: unknown[]) => putMock(...a),
    patch: (...a: unknown[]) => patchMock(...a),
    delete: (...a: unknown[]) => deleteMock(...a),
  },
}));

import { committeesApi } from "@/api/committees";

beforeEach(() => {
  getMock.mockReset().mockResolvedValue({ data: {} });
  postMock.mockReset().mockResolvedValue({ data: {} });
  putMock.mockReset().mockResolvedValue({ data: {} });
  patchMock.mockReset().mockResolvedValue({ data: {} });
  deleteMock.mockReset().mockResolvedValue({ data: {} });
});

describe("committeesApi срез-2", () => {
  it("getAttendance requests the meeting attendance list", async () => {
    const rows = [
      { id: "a1", meeting_id: "m1", person_id: "p1", present: true },
    ];
    getMock.mockResolvedValue({ data: rows });

    const result = await committeesApi.getAttendance("m1");

    expect(getMock).toHaveBeenCalledWith("/committees/meetings/m1/attendance");
    expect(result).toEqual(rows);
  });

  it("putAttendance sends items in the request body", async () => {
    const items = [
      { person_id: "p1", present: true },
      { person_id: "p2", present: false },
    ];
    const rows = items.map((i, idx) => ({
      id: `a${idx}`,
      meeting_id: "m1",
      ...i,
    }));
    putMock.mockResolvedValue({ data: rows });

    const result = await committeesApi.putAttendance("m1", items);

    expect(putMock).toHaveBeenCalledWith("/committees/meetings/m1/attendance", {
      items,
    });
    expect(result).toEqual(rows);
  });

  it("holdMeeting PATCHes the meeting status to held", async () => {
    const meeting = {
      id: "m1",
      committee_id: "c1",
      scheduled_at: "2026-07-14T00:00:00Z",
      status: "held",
    };
    patchMock.mockResolvedValue({ data: meeting });

    const result = await committeesApi.holdMeeting("m1");

    expect(patchMock).toHaveBeenCalledWith("/committees/meetings/m1", {
      status: "held",
    });
    expect(result).toEqual(meeting);
  });

  it("castVote posts person_id and choice", async () => {
    const vote = {
      id: "v1",
      decision_id: "d1",
      person_id: "p1",
      choice: "for" as const,
    };
    postMock.mockResolvedValue({ data: vote });

    const result = await committeesApi.castVote("d1", "p1", "for");

    expect(postMock).toHaveBeenCalledWith("/committees/decisions/d1/votes", {
      person_id: "p1",
      choice: "for",
    });
    expect(result).toEqual(vote);
  });

  it("getVotes requests the vote summary for a decision", async () => {
    const summary = {
      decision_id: "d1",
      votes_for: 2,
      votes_against: 1,
      votes_abstain: 0,
      outcome: "carried" as const,
      votes: [],
    };
    getMock.mockResolvedValue({ data: summary });

    const result = await committeesApi.getVotes("d1");

    expect(getMock).toHaveBeenCalledWith("/committees/decisions/d1/votes");
    expect(result).toEqual(summary);
  });

  it("listProtocols requests the journal with default paging params", async () => {
    const page = { items: [], total: 0, limit: 100, offset: 0 };
    getMock.mockResolvedValue({ data: page });

    const result = await committeesApi.listProtocols();

    expect(getMock).toHaveBeenCalledWith("/committees/protocols", {
      params: { limit: 100, offset: 0 },
    });
    expect(result).toEqual(page);
  });

  it("listProtocols passes committee_id and overrides paging when provided", async () => {
    const page = { items: [], total: 0, limit: 10, offset: 5 };
    getMock.mockResolvedValue({ data: page });

    await committeesApi.listProtocols({
      committee_id: "c1",
      limit: 10,
      offset: 5,
    });

    expect(getMock).toHaveBeenCalledWith("/committees/protocols", {
      params: { committee_id: "c1", limit: 10, offset: 5 },
    });
  });
});
