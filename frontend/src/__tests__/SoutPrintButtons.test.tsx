import { describe, expect, it, vi, beforeEach } from "vitest";

import { soutApi } from "@/api/sout";

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn() },
}));

describe("soutApi print download methods", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("downloadSummary requests blob with format param", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: new Blob(["x"]) });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:1");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    await soutApi.downloadSummary("c1", "pdf");

    expect(apiClient.get).toHaveBeenCalledWith(
      "/sout/c1/summary/print",
      expect.objectContaining({ params: { format: "pdf" }, responseType: "blob" }),
    );
  });

  it("downloadCard requests blob for workplace", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: new Blob(["x"]) });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:1");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    await soutApi.downloadCard("w1", "docx", "РМ-01");

    expect(apiClient.get).toHaveBeenCalledWith(
      "/sout/workplaces/w1/card/print",
      expect.objectContaining({ params: { format: "docx" }, responseType: "blob" }),
    );
  });
});
