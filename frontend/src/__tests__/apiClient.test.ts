/* eslint-disable no-restricted-imports -- axios-mock-adapter must wrap the same axios instance as the app */
import axios from "axios";
import MockAdapter from "axios-mock-adapter";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { appConfig } from "@/config/env";
import { tenantStorage } from "@/api/tenantStorage";
import { tokenStorage } from "@/api/tokenStorage";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

describe("apiClient", () => {
  beforeEach(() => {
    tokenStorage.clear();
    tenantStorage.clear();
  });

  it("injects auth and tenant headers", async () => {
    tokenStorage.setTokens({ accessToken: "access-token", expiresIn: 10 });
    tenantStorage.setTenant({ slug: "severstroy", site: "Северный кластер" });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply((config) => {
      expect(config.headers?.Authorization).toBe("Bearer access-token");
      expect(config.headers?.["X-Tenant"]).toBe("severstroy");
      expect(config.headers?.["X-Site"]).toBeUndefined();
      return [200, {}];
    });

    await apiClient.get("/documents");
    mock.restore();
  });

  it("uses актуальный tenant после переключения контура", async () => {
    const mock = new MockAdapter(apiClient);
    mock
      .onGet("/documents")
      .reply((config) => [200, { tenant: config.headers?.["X-Tenant"] }]);

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
      message: "Выберите контур перед выполнением запроса.",
    });

    mock.restore();
  });

  it("allows whitelisted routes without tenant", async () => {
    const mock = new MockAdapter(apiClient);

    mock.onGet("/health").reply((config) => {
      expect(config.headers?.["X-Tenant"]).toBeUndefined();
      expect(config.headers?.["X-Site"]).toBeUndefined();
      return [200, { status: "ok" }];
    });

    await apiClient.get("/health");

    mock.restore();
  });

  it("injects tenant header for auth profile routes", async () => {
    tenantStorage.setTenant({ slug: "demo" });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/auth/me").reply((config) => {
      expect(config.headers?.["X-Tenant"]).toBe("demo");
      return [200, {}];
    });

    await apiClient.get("/auth/me");

    mock.restore();
  });

  it("maps api errors from responses", async () => {
    tenantStorage.setTenant({ slug: "severstroy", site: "Северный кластер" });

    const mock = new MockAdapter(apiClient);
    mock
      .onGet("/documents")
      .reply(409, { message: "Conflict", code: "CONFLICT" });

    await expect(apiClient.get("/documents")).rejects.toMatchObject({
      status: 409,
      code: "CONFLICT",
      message: "Conflict",
    });

    mock.restore();
  });

  it("sends tenant header during silent refresh", async () => {
    const refreshUrl = `${appConfig.apiBaseUrl}/auth/refresh`;
    const nextAccessToken = [
      "header",
      btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 60 }))
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/g, ""),
      "signature",
    ].join(".");

    tokenStorage.setTokens({ accessToken: "expired-access", expiresIn: 10 });
    tenantStorage.setTenant({ slug: "demo" });

    const apiMock = new MockAdapter(apiClient);
    const axiosMock = new MockAdapter(axios);

    apiMock
      .onGet("/documents")
      .replyOnce(401)
      .onGet("/documents")
      .replyOnce(200, { ok: true });
    axiosMock.onPost(refreshUrl).reply((config) => {
      expect(config.headers?.["X-Tenant"]).toBe("demo");
      return [200, { access_token: nextAccessToken }];
    });

    const response = await apiClient.get<{ ok: boolean }>("/documents");

    expect(response.data).toEqual({ ok: true });
    expect(tokenStorage.getAccessToken()).toBe(nextAccessToken);

    apiMock.restore();
    axiosMock.restore();
  });

  it("does not call refresh endpoint when 401 arrives without access token", async () => {
    tenantStorage.setTenant({ slug: "demo" });

    const refreshUrl = `${appConfig.apiBaseUrl}/auth/refresh`;
    const apiMock = new MockAdapter(apiClient);
    const axiosMock = new MockAdapter(axios);

    apiMock.onGet("/documents").replyOnce(401);
    axiosMock
      .onPost(refreshUrl)
      .reply(200, { access_token: "should-not-be-used" });

    await expect(apiClient.get("/documents")).rejects.toMatchObject({
      status: 401,
    });
    expect(axiosMock.history.post).toHaveLength(0);

    apiMock.restore();
    axiosMock.restore();
  });

  it("normalizes structured backend errors including contract metadata", async () => {
    tenantStorage.setTenant({ slug: "severstroy", site: "Северный кластер" });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply(422, {
      code: "VALIDATION_ERROR",
      type: "validation",
      message: "Validation failed",
      details: { entity: "document" },
      field_errors: [
        { field: "template_code", message: "Required", code: "required" },
      ],
      correlation_id: "corr-123",
      timestamp: "2026-03-19T00:00:00Z",
    });

    await expect(apiClient.get("/documents")).rejects.toMatchObject({
      status: 422,
      code: "VALIDATION_ERROR",
      type: "validation",
      message: "Validation failed",
      correlation_id: "corr-123",
      timestamp: "2026-03-19T00:00:00Z",
      field_errors: [
        { field: "template_code", message: "Required", code: "required" },
      ],
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

describe("apiClient: контекст ведомого клиента (BIZ-49 разд. 49.3)", () => {
  beforeEach(async () => {
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    managedClientStorage.clear();
    tenantStorage.clear();
    tokenStorage.clear();
  });

  it("подставляет X-Managed-Client, когда контекст активен", async () => {
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    tenantStorage.setTenant({ slug: "severstroy" });
    managedClientStorage.set({ clientId: "mc1", clientName: "Ромашка" });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply((config) => {
      expect(config.headers?.["X-Managed-Client"]).toBe("mc1");
      return [200, {}];
    });
    await apiClient.get("/documents");
    mock.restore();
  });

  it("без контекста заголовка нет", async () => {
    tenantStorage.setTenant({ slug: "severstroy" });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply((config) => {
      expect(config.headers?.["X-Managed-Client"]).toBeUndefined();
      return [200, {}];
    });
    await apiClient.get("/documents");
    mock.restore();
  });

  it("смена контура сбрасывает контекст клиента: заголовок не уедет к соседу", async () => {
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    tenantStorage.setTenant({ slug: "severstroy" });
    managedClientStorage.set({ clientId: "mc1", clientName: "Ромашка" });

    tenantStorage.setTenant({ slug: "uralenergo" });

    expect(managedClientStorage.get()).toBeNull();
    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply((config) => {
      expect(config.headers?.["X-Managed-Client"]).toBeUndefined();
      return [200, {}];
    });
    await apiClient.get("/documents");
    mock.restore();
  });
});

describe("apiClient: ключ от контура Dedicated-клиента (срез-225)", () => {
  const contour = {
    tenantSlug: "romashka",
    accessToken: "contour-token",
    role: "ot_specialist",
    displayName: "Иванов (Северстрой)",
  };

  beforeEach(async () => {
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    managedClientStorage.clear();
    tenantStorage.clear();
    tokenStorage.clear();
  });

  it("запрос данных уходит по ключу контура: и токен, и арендатор — клиента", async () => {
    // Без этого вход в контекст Dedicated-клиента открывал ПУСТОТУ: данные
    // лежат в другом арендаторе, куда свой токен не пускает.
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    tenantStorage.setTenant({ slug: "severstroy" });
    tokenStorage.setTokens({ accessToken: "own-token", expiresIn: 600 });
    managedClientStorage.set({
      clientId: "mc1",
      clientName: "Ромашка",
      contour,
    });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply((config) => {
      expect(config.headers?.Authorization).toBe("Bearer contour-token");
      expect(config.headers?.["X-Tenant"]).toBe("romashka");
      return [200, {}];
    });
    await apiClient.get("/documents");
    mock.restore();
  });

  it("в контуре клиента заголовок «ведомый клиент» не едет", async () => {
    // Строки такого клиента в ЕГО собственном контуре нет, а метка
    // делегирования лежит в токене (срез-215).
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    tenantStorage.setTenant({ slug: "severstroy" });
    tokenStorage.setTokens({ accessToken: "own-token", expiresIn: 600 });
    managedClientStorage.set({
      clientId: "mc1",
      clientName: "Ромашка",
      contour,
    });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply((config) => {
      expect(config.headers?.["X-Managed-Client"]).toBeUndefined();
      return [200, {}];
    });
    await apiClient.get("/documents");
    mock.restore();
  });

  it("выход из контекста уходит от личности аутсорсера, иначе выйти нельзя", async () => {
    // Портфель и сам контекст живут в пространстве аутсорсера: уйди этот
    // запрос по ключу контура, специалист застрял бы в чужом контуре.
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    tenantStorage.setTenant({ slug: "severstroy" });
    tokenStorage.setTokens({ accessToken: "own-token", expiresIn: 600 });
    managedClientStorage.set({
      clientId: "mc1",
      clientName: "Ромашка",
      contour,
    });

    const mock = new MockAdapter(apiClient);
    mock.onDelete("/managed-clients/context").reply((config) => {
      expect(config.headers?.Authorization).toBe("Bearer own-token");
      expect(config.headers?.["X-Tenant"]).toBe("severstroy");
      return [204];
    });
    await apiClient.delete("/managed-clients/context");
    mock.restore();
  });

  it("у Lightweight-клиента ключа нет — работаем своим токеном", async () => {
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    tenantStorage.setTenant({ slug: "severstroy" });
    tokenStorage.setTokens({ accessToken: "own-token", expiresIn: 600 });
    managedClientStorage.set({ clientId: "mc2", clientName: "Василёк" });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply((config) => {
      expect(config.headers?.Authorization).toBe("Bearer own-token");
      expect(config.headers?.["X-Tenant"]).toBe("severstroy");
      expect(config.headers?.["X-Managed-Client"]).toBe("mc2");
      return [200, {}];
    });
    await apiClient.get("/documents");
    mock.restore();
  });

  it("истёкший контекст больше не открывает чужой контур", async () => {
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    tenantStorage.setTenant({ slug: "severstroy" });
    tokenStorage.setTokens({ accessToken: "own-token", expiresIn: 600 });
    managedClientStorage.set({
      clientId: "mc1",
      clientName: "Ромашка",
      expiresAt: new Date(Date.now() - 1000).toISOString(),
      contour,
    });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/documents").reply((config) => {
      expect(config.headers?.Authorization).toBe("Bearer own-token");
      expect(config.headers?.["X-Tenant"]).toBe("severstroy");
      return [200, {}];
    });
    await apiClient.get("/documents");
    mock.restore();
  });

  it("401 по ключу контура гасит контекст и НЕ зовёт обновление токена", async () => {
    // Обновление вернуло бы токен личности АУТСОРСЕРА, запрос повторился бы с
    // ним в контуре клиента — и специалист работал бы там под своим именем.
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    tenantStorage.setTenant({ slug: "severstroy" });
    tokenStorage.setTokens({ accessToken: "own-token", expiresIn: 600 });
    managedClientStorage.set({
      clientId: "mc1",
      clientName: "Ромашка",
      contour,
    });

    const mock = new MockAdapter(apiClient);
    let refreshCalls = 0;
    mock.onPost("/auth/refresh").reply(() => {
      refreshCalls += 1;
      return [200, { access_token: "new-own-token" }];
    });
    mock.onGet("/documents").reply(401, { code: "UNAUTHORIZED" });

    await expect(apiClient.get("/documents")).rejects.toMatchObject({
      status: 401,
    });
    expect(refreshCalls).toBe(0);
    expect(managedClientStorage.get()).toBeNull();
    mock.restore();
  });
});

describe("apiClient: истёкший контекст клиента (BIZ-49 срез-10)", () => {
  it("отказ «время вышло» гасит локальный контекст", async () => {
    // Иначе баннер продолжает обещать работу «от имени», каждый запрос
    // получает отказ, а данные при этом уже НЕ отфильтрованы.
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    tenantStorage.setTenant({ slug: "severstroy" });
    managedClientStorage.set({ clientId: "mc1", clientName: "Ромашка" });

    const mock = new MockAdapter(apiClient);
    mock.onGet("/persons").reply(403, {
      detail: { code: "MANAGED_CLIENT_CONTEXT_EXPIRED", message: "Срок истёк" },
    });

    await expect(apiClient.get("/persons")).rejects.toBeDefined();
    expect(managedClientStorage.get()).toBeNull();
    mock.restore();
  });

  it("обычный отказ 403 контекст не трогает", async () => {
    const { managedClientStorage } = await import("@/api/managedClientStorage");
    tenantStorage.setTenant({ slug: "severstroy" });
    managedClientStorage.set({ clientId: "mc1", clientName: "Ромашка" });

    const mock = new MockAdapter(apiClient);
    mock
      .onGet("/persons")
      .reply(403, { detail: { code: "FORBIDDEN", message: "Нет прав" } });

    await expect(apiClient.get("/persons")).rejects.toBeDefined();
    expect(managedClientStorage.get()).not.toBeNull();
    mock.restore();
  });
});
