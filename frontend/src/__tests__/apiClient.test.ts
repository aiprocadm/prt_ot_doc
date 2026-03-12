import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { tenantStorage } from "@/api/tenantStorage";
import { tokenStorage } from "@/api/tokenStorage";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn()
  }
}));

describe("apiClient", () => {
  beforeEach(() => {
    tokenStorage.clear();
    tenantStorage.clear();
  });

  it("injects auth and tenant headers", async () => {
    tokenStorage.setTokens({ accessToken: "access-token", refreshToken: "refresh-token", expiresIn: 10 });
    tenantStorage.setTenant({ slug: "severstroy", site: "Северный кластер" });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply((config) => {
      expect(config.headers?.Authorization).toBe("Bearer access-token");
      expect(config.headers?.["X-Tenant"]).toBe("severstroy");
      expect(config.headers?.["X-Site"]).toBe("Северный кластер");
      return [200, {}];
    });

    await apiClient.get("/documents");
    mock.restore();
  });

  it("uses актуальный tenant после переключения контура", async () => {
    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply((config) => [200, { tenant: config.headers?.["X-Tenant"] }]);

    tenantStorage.setTenant({ slug: "severstroy", site: "Северный кластер" });
    const first = await apiClient.get<{ tenant: string }>("/documents");
    expect(first.data.tenant).toBe("severstroy");

    tenantStorage.setTenant({ slug: "uralenergo", site: "Урал" });
    const second = await apiClient.get<{ tenant: string }>("/documents");
    expect(second.data.tenant).toBe("uralenergo");

    mock.restore();
  });

  it("blocks requests without tenant for protected routes", async () => {
    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply(200, {});

    await expect(apiClient.get("/documents")).rejects.toMatchObject({
      status: 0,
      message: "Выберите контур перед выполнением запроса."
    });

    mock.restore();
  });

  it("allows whitelisted routes without tenant", async () => {
    const mock = new MockAdapter(apiClient);

    mock.onGet("/auth/login").reply((config) => {
      expect(config.headers?.["X-Tenant"]).toBeUndefined();
      expect(config.headers?.["X-Site"]).toBeUndefined();
      return [200, {}];
    });

    mock.onGet("/health").reply((config) => {
      expect(config.headers?.["X-Tenant"]).toBeUndefined();
      expect(config.headers?.["X-Site"]).toBeUndefined();
      return [200, { status: "ok" }];
    });

    await apiClient.get("/auth/login");
    await apiClient.get("/health");

    mock.restore();
  });

  it("maps api errors from responses", async () => {
    tenantStorage.setTenant({ slug: "severstroy", site: "Северный кластер" });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply(409, { message: "Conflict", code: "CONFLICT" });

    await expect(apiClient.get("/documents")).rejects.toMatchObject({
      status: 409,
      code: "CONFLICT",
      message: "Conflict"
    });

    mock.restore();
  });

  it("calls the backend health endpoint", async () => {
    const mock = new MockAdapter(apiClient);
    mock.onGet("/health").reply(200, { status: "ok" });

    const response = await apiClient.get("/health");

    expect(response.data).toEqual({ status: "ok" });
    mock.restore();
  });
});
