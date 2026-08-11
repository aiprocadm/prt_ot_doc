import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { registerPwa } from "@/pwa/register";

const mocks = vi.hoisted(() => ({
  registerSW: vi.fn()
}));

vi.mock("virtual:pwa-register", () => ({
  registerSW: mocks.registerSW
}));

const getOnRegistered = (): ((registration: ServiceWorkerRegistration | undefined) => void) => {
  const call = mocks.registerSW.mock.calls.at(-1)?.[0];
  if (!call?.onRegistered) throw new Error("registerSW не был вызван с onRegistered");
  return call.onRegistered as (registration: ServiceWorkerRegistration | undefined) => void;
};

describe("registerPwa: подхват новой версии без ожидания часа", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubEnv("DEV", false);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  it("проверяет обновление при возврате фокуса на вкладку", () => {
    registerPwa();
    const registration = { update: vi.fn().mockResolvedValue(undefined) };
    getOnRegistered()(registration as unknown as ServiceWorkerRegistration);

    window.dispatchEvent(new Event("focus"));
    expect(registration.update).toHaveBeenCalledTimes(1);
  });

  it("проверяет обновление, когда вкладка снова становится видимой", () => {
    registerPwa();
    const registration = { update: vi.fn().mockResolvedValue(undefined) };
    getOnRegistered()(registration as unknown as ServiceWorkerRegistration);

    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(registration.update).toHaveBeenCalledTimes(1);
  });

  it("проверяет обновление по таймеру не реже, чем раз в 15 минут", () => {
    registerPwa();
    const registration = { update: vi.fn().mockResolvedValue(undefined) };
    getOnRegistered()(registration as unknown as ServiceWorkerRegistration);

    vi.advanceTimersByTime(15 * 60 * 1000);
    expect(registration.update).toHaveBeenCalled();
  });
});
