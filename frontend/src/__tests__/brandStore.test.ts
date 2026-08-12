import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AppBrand } from "@/api/appBrand";
import {
  applyBrandTheme,
  PLATFORM_FALLBACK,
  useBrandStore,
} from "@/stores/brand";

const getAppBrandMock = vi.fn();

vi.mock("@/api/appBrand", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/appBrand")>()),
  getAppBrand: () => getAppBrandMock(),
}));

const partnerBrand: AppBrand = {
  app_name: "Охрана труда «Партнёр»",
  primary_color: "210 90% 40%",
  support_email: "help@partner.ru",
  source: "reseller",
};

describe("бренд приложения (BIZ-52 срез-4)", () => {
  beforeEach(() => {
    getAppBrandMock.mockReset();
    // Хранилище кэширует на сеанс: без сброса следующий тест прошёл бы
    // вхолостую на ответе предыдущего (грабля BIZ-61 срез-5).
    useBrandStore.getState().reset();
    document.documentElement.style.removeProperty("--primary");
  });

  it("до ответа сервера действует платформенное умолчание", () => {
    // Пустая шапка читается как поломка загрузки, поэтому имя есть всегда.
    expect(useBrandStore.getState().brand.app_name).toBe(
      PLATFORM_FALLBACK.app_name,
    );
  });

  it("подставляет бренд партнёра после загрузки", async () => {
    getAppBrandMock.mockResolvedValue(partnerBrand);

    await useBrandStore.getState().load();

    expect(useBrandStore.getState().brand.app_name).toBe(
      "Охрана труда «Партнёр»",
    );
  });

  it("при ошибке остаётся на платформенном бренде, а не пустеет", async () => {
    getAppBrandMock.mockRejectedValue(new Error("сеть"));

    await useBrandStore.getState().load();

    const state = useBrandStore.getState();
    expect(state.brand.app_name).toBe(PLATFORM_FALLBACK.app_name);
    expect(state.loaded).toBe(true);
  });

  it("не ходит на сервер повторно за уже загруженным брендом", async () => {
    getAppBrandMock.mockResolvedValue(partnerBrand);

    await useBrandStore.getState().load();
    await useBrandStore.getState().load();

    expect(getAppBrandMock).toHaveBeenCalledTimes(1);
  });

  it("применяет цвет в ту же переменную, которую использует тема", () => {
    applyBrandTheme(partnerBrand);

    expect(
      document.documentElement.style.getPropertyValue("--primary"),
    ).toBe("210 90% 40%");
  });

  it("ставит имя приложения в заголовок вкладки", () => {
    applyBrandTheme(partnerBrand);

    expect(document.title).toBe("Охрана труда «Партнёр»");
  });
});
