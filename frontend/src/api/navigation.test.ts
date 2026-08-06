import MockAdapter from "axios-mock-adapter";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { sendUxMetric } from "@/api/navigation";
import { tenantStorage } from "@/api/tenantStorage";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

describe("sendUxMetric", () => {
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

  it("не показывает тост при 404: метрики — best-effort, эндпоинт может отсутствовать", async () => {
    mock.onPost("/analytics/ux-events").reply(404, {
      code: "NOT_FOUND",
      type: "not_found",
      message: "Not Found",
    });

    await expect(sendUxMetric("nav.landing")).resolves.toBeUndefined();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("обычные запросы без silent-флага по-прежнему показывают тост на 404", async () => {
    mock.onGet("/documents/missing").reply(404, {
      code: "NOT_FOUND",
      type: "not_found",
      message: "Not Found",
    });

    await expect(apiClient.get("/documents/missing")).rejects.toMatchObject({
      status: 404,
    });
    expect(toast.error).toHaveBeenCalled();
  });
});
