import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AppBrand } from "@/api/appBrand";
import {
  applyBrandTheme,
  applyFavicon,
  applyManifest,
  PLATFORM_FALLBACK,
  useBrandStore,
} from "@/stores/brand";

const getAppBrandMock = vi.fn();
const getBrandImageUrlMock = vi.fn();

vi.mock("@/api/appBrand", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/appBrand")>()),
  getAppBrand: () => getAppBrandMock(),
  getBrandImageUrl: (kind: "logo" | "favicon") => getBrandImageUrlMock(kind),
}));

const partnerBrand: AppBrand = {
  app_name: "Охрана труда «Партнёр»",
  primary_color: "210 90% 40%",
  support_email: "help@partner.ru",
  source: "reseller",
  has_logo: false,
  has_favicon: false,
};

describe("бренд приложения (BIZ-52 срезы 4 и 6)", () => {
  beforeEach(() => {
    getAppBrandMock.mockReset();
    getBrandImageUrlMock.mockReset();
    // jsdom не реализует object-URL — подменяем, иначе тесты картинок падают
    // на отсутствующей функции, а не на проверяемом свойстве.
    URL.revokeObjectURL = vi.fn();
    // Хранилище кэширует на сеанс: без сброса следующий тест прошёл бы
    // вхолостую на ответе предыдущего (грабля BIZ-61 срез-5).
    useBrandStore.getState().reset();
    document.documentElement.style.removeProperty("--primary");
    document.querySelector('link[rel="icon"]')?.remove();
  });

  it("до ответа сервера действует платформенное умолчание", () => {
    // Пустая шапка читается как поломка загрузки, поэтому имя есть всегда.
    expect(useBrandStore.getState().brand.app_name).toBe(
      PLATFORM_FALLBACK.app_name,
    );
    expect(useBrandStore.getState().logoUrl).toBeNull();
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

  it("без признаков картинок за ними не ходит вовсе", async () => {
    // У большинства арендаторов картинок нет: лишние запросы за 404 были бы
    // платой каждого за возможность немногих.
    getAppBrandMock.mockResolvedValue(partnerBrand);

    await useBrandStore.getState().load();

    expect(getBrandImageUrlMock).not.toHaveBeenCalled();
  });

  it("логотип по признаку попадает в хранилище", async () => {
    getAppBrandMock.mockResolvedValue({ ...partnerBrand, has_logo: true });
    getBrandImageUrlMock.mockResolvedValue("blob:logo");

    await useBrandStore.getState().load();

    expect(getBrandImageUrlMock).toHaveBeenCalledWith("logo");
    expect(useBrandStore.getState().logoUrl).toBe("blob:logo");
  });

  it("favicon по признаку ставится в шапку документа", async () => {
    getAppBrandMock.mockResolvedValue({ ...partnerBrand, has_favicon: true });
    getBrandImageUrlMock.mockResolvedValue("blob:favicon");

    await useBrandStore.getState().load();

    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    expect(link?.getAttribute("href")).toBe("blob:favicon");
  });

  it("несуществующая картинка не роняет загрузку бренда", async () => {
    getAppBrandMock.mockResolvedValue({ ...partnerBrand, has_logo: true });
    getBrandImageUrlMock.mockResolvedValue(null);

    await useBrandStore.getState().load();

    const state = useBrandStore.getState();
    expect(state.loaded).toBe(true);
    expect(state.logoUrl).toBeNull();
  });

  it("применяет цвет в ту же переменную, которую использует тема", () => {
    applyBrandTheme(partnerBrand);

    expect(document.documentElement.style.getPropertyValue("--primary")).toBe(
      "210 90% 40%",
    );
  });

  it("ставит имя приложения в заголовок вкладки", () => {
    applyBrandTheme(partnerBrand);

    expect(document.title).toBe("Охрана труда «Партнёр»");
  });

  it("favicon ставится и при отсутствии штатной ссылки в разметке", () => {
    applyFavicon("blob:x");

    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    expect(link?.getAttribute("href")).toBe("blob:x");
  });

  // --- манифест PWA (срез-14) ---

  it("манифест указывает на арендатора", () => {
    // Ярлык на домашнем экране — самое заметное место, где разд. 52.2 требует
    // подмены вендора. Манифест браузер грузит сам, поэтому слаг идёт в адресе.
    applyManifest("acme");

    const link = document.querySelector<HTMLLinkElement>(
      'link[rel="manifest"]',
    );
    expect(link?.getAttribute("href")).toBe(
      "/api/v1/public/manifest.webmanifest?tenant=acme",
    );
  });

  it("без арендатора манифест всё равно подключается", () => {
    // Экран входа до выбора арендатора: ярлык должен быть валидным, просто
    // платформенным.
    applyManifest(null);

    const link = document.querySelector<HTMLLinkElement>(
      'link[rel="manifest"]',
    );
    expect(link?.getAttribute("href")).toBe(
      "/api/v1/public/manifest.webmanifest",
    );
  });

  it("слаг экранируется", () => {
    applyManifest("под чертой");

    const link = document.querySelector<HTMLLinkElement>(
      'link[rel="manifest"]',
    );
    expect(link?.getAttribute("href")).toContain("%20");
  });

  it("повторный вызов не плодит ссылок", () => {
    applyManifest("acme");
    applyManifest("beta");

    const links = document.querySelectorAll('link[rel="manifest"]');
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toContain("tenant=beta");
  });
});
