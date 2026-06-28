import { beforeEach, describe, expect, it, vi } from "vitest";

import { soutApi } from "@/api/sout";

vi.mock("@/api/client", () => ({
  apiClient: { post: vi.fn() },
}));

describe("soutApi import methods", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("previewImport posts FormData to the preview endpoint", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { campaign_id: "c1", rows: [], new_count: 0, changed_count: 0, unchanged_count: 0, removed_count: 0, error_count: 0, can_apply: true },
    });
    const file = new File(["x"], "r.csv", { type: "text/csv" });

    const out = await soutApi.previewImport("c1", file);

    expect(apiClient.post).toHaveBeenCalledWith(
      "/sout/c1/import/preview",
      expect.any(FormData),
    );
    expect(out.campaign_id).toBe("c1");
  });

  it("applyImport posts FormData to the apply endpoint", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { campaign_id: "c1", created: 1, updated: 0, skipped: 0, removed_detected: 0, errors: [] },
    });
    const file = new File(["x"], "r.csv", { type: "text/csv" });

    const out = await soutApi.applyImport("c1", file);

    expect(apiClient.post).toHaveBeenCalledWith(
      "/sout/c1/import/apply",
      expect.any(FormData),
    );
    expect(out.created).toBe(1);
  });
});
