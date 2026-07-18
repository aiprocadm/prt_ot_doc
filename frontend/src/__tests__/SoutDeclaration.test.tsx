import { describe, expect, it, vi, beforeEach } from "vitest";

import { soutApi } from "@/api/sout";

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn() },
}));

describe("soutApi declaration methods", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("getDeclaration calls the preview endpoint", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { campaign_id: "c1", campaign_name: "СОУТ", eligible: [], ineligible: [], eligible_count: 0, ineligible_count: 0 },
    });

    const out = await soutApi.getDeclaration("c1");

    expect(apiClient.get).toHaveBeenCalledWith("/sout/c1/declaration");
    expect(out.campaign_id).toBe("c1");
  });

  it("downloadDeclaration requests blob with format param", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: new Blob(["x"]) });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:1");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    await soutApi.downloadDeclaration("c1", "pdf");

    expect(apiClient.get).toHaveBeenCalledWith(
      "/sout/c1/declaration/print",
      expect.objectContaining({ params: { format: "pdf" }, responseType: "blob" }),
    );
  });
});
