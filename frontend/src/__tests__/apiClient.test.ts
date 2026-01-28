import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { appConfig } from "@/config/env";
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

    const interceptor = apiClient.interceptors.request.handlers[0]?.fulfilled as (config: Record<string, unknown>) => Promise<unknown>;
    const config = { headers: {}, url: "/documents", baseURL: appConfig.apiBaseUrl };
    const result = (await interceptor(config)) as { headers: Record<string, string> };

    expect(result.headers.Authorization).toBe("Bearer access-token");
    expect(result.headers["X-Tenant"]).toBe("severstroy");
    expect(result.headers["X-Site"]).toBe("Северный кластер");
  });

  it("blocks requests without tenant for protected routes", async () => {
    const interceptor = apiClient.interceptors.request.handlers[0]?.fulfilled as (config: Record<string, unknown>) => Promise<unknown>;
    await expect(interceptor({ headers: {}, url: "/documents", baseURL: appConfig.apiBaseUrl })).rejects.toMatchObject({
      code: "TENANT_REQUIRED"
    });
  });

  it("allows whitelisted routes without tenant", async () => {
    const interceptor = apiClient.interceptors.request.handlers[0]?.fulfilled as (config: Record<string, unknown>) => Promise<unknown>;

    const authResult = (await interceptor({ headers: {}, url: "/auth/login", baseURL: appConfig.apiBaseUrl })) as {
      headers: Record<string, string>;
    };
    const healthResult = (await interceptor({ headers: {}, url: "/health", baseURL: appConfig.apiBaseUrl })) as {
      headers: Record<string, string>;
    };

    expect(authResult.headers).toEqual({});
    expect(healthResult.headers).toEqual({});
  });

  it("maps api errors from responses", async () => {
    const responseInterceptor = apiClient.interceptors.response.handlers[0]?.rejected as (error: unknown) => Promise<unknown>;
    await expect(
      responseInterceptor({
        response: { status: 409, data: { message: "Conflict", code: "CONFLICT" } },
        message: "Request failed",
        config: { url: "/documents" }
      })
    ).rejects.toMatchObject({
      status: 409,
      code: "CONFLICT",
      message: "Conflict"
    });
  });
});
