import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDocumentsStore } from "@/stores/documents";

const getMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

describe("documents store", () => {
  beforeEach(() => {
    getMock.mockReset();
    useDocumentsStore.getState().reset();
  });

  it("normalizes legacy paginated documents responses", async () => {
    getMock.mockResolvedValue({
      data: {
        items: [{ id: "doc-1", name: "Doc", status: "ready" }],
        total: 12,
        limit: 50,
        offset: 50,
      },
    });

    await useDocumentsStore.getState().list();

    const state = useDocumentsStore.getState();
    expect(state.items).toHaveLength(1);
    expect(state.pagination).toEqual({ page: 2, page_size: 50, total: 12 });
  });

  it("falls back to safe defaults for malformed responses", async () => {
    getMock.mockResolvedValue({
      data: {
        items: null,
        pagination: null,
      },
    });

    await useDocumentsStore.getState().list();

    const state = useDocumentsStore.getState();
    expect(state.items).toEqual([]);
    expect(state.pagination).toEqual({ page: 1, page_size: 10, total: 0 });
  });
});