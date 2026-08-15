import { createWithEqualityFn } from "zustand/traditional";

import { getAppBrand, getBrandImageUrl, type AppBrand } from "@/api/appBrand";

/**
 * Бренд приложения (BIZ-52 срезы 4 и 6, ТЗ Доп. №1 разд. 52.2).
 *
 * Отдельное хранилище, а не контекст: имя и цвет нужны и экрану входа (он вне
 * защищённого дерева), и шапке, и заголовку вкладки. Контекст пришлось бы
 * поднимать выше роутера — и он ломался бы от перестановки провайдеров.
 * Та же причина, что у хранилища модулей.
 *
 * **Умолчание — платформенное, а не пустое.** Пока ответ не пришёл, приложение
 * обязано как-то называться: пустая шапка читается как поломка загрузки.
 */
export const PLATFORM_FALLBACK: AppBrand = {
  app_name: "Платформа ОТ/ПБ",
  primary_color: "222.2 47.4% 11.2%",
  support_email: null,
  source: "platform",
  has_logo: false,
  has_favicon: false,
};

interface BrandState {
  brand: AppBrand;
  /** Адрес логотипа в памяти страницы; `null` — логотипа нет. */
  logoUrl: string | null;
  loaded: boolean;
  loading: boolean;
  load: () => Promise<void>;
  reset: () => void;
}

const initial = {
  brand: PLATFORM_FALLBACK,
  logoUrl: null as string | null,
  loaded: false,
  loading: false,
};

export const useBrandStore = createWithEqualityFn<BrandState>((set, get) => ({
  ...initial,
  load: async () => {
    if (get().loading || get().loaded) return;
    set({ loading: true });
    try {
      const brand = await getAppBrand();
      set({ brand, loaded: true, loading: false });
      // Картинки — после текста и только по признакам: у большинства
      // арендаторов их нет, и лишние запросы за 404 были бы платой каждого
      // за возможность немногих.
      if (brand.has_favicon) {
        const faviconUrl = await getBrandImageUrl("favicon");
        if (faviconUrl) applyFavicon(faviconUrl);
      }
      if (brand.has_logo) {
        const logoUrl = await getBrandImageUrl("logo");
        if (logoUrl) set({ logoUrl });
      }
    } catch {
      // Не закрываемся при ошибке: приложение под платформенным брендом
      // работоспособно, а пустая шапка — нет. Ошибку уже показал общий
      // перехватчик запросов.
      set({ loaded: true, loading: false });
    }
  },
  reset: () => {
    const previous = get().logoUrl;
    if (previous) {
      try {
        URL.revokeObjectURL(previous);
      } catch {
        // адрес мог быть уже отозван — не повод ронять сброс
      }
    }
    set({ ...initial });
  },
}));

/**
 * Применить бренд к теме. Цвет приходит HSL-триплетом ровно в том виде, в каком
 * его ждёт переменная `--primary` — без перевода форматов, который однажды
 * разошёлся бы с интерфейсом.
 */
export const applyBrandTheme = (brand: AppBrand): void => {
  if (typeof document === "undefined") return;
  document.documentElement.style.setProperty("--primary", brand.primary_color);
  document.title = brand.app_name;
};

/**
 * Указать на манифест арендатора вместо собранного на сборке (срез-14).
 *
 * До этого манифест зашивался при сборке с именем и иконками вендора, поэтому
 * клиент партнёра, добавивший приложение на домашний экран, получал ярлык
 * вендора — самое заметное место, где разд. 52.2 требует обратного.
 *
 * Слаг уходит параметром адреса: манифест браузер грузит САМ, заголовок
 * арендатора в такой запрос не поставить. Без слага сервер вернул бы бренд
 * не того арендатора.
 */
export const applyManifest = (tenantSlug: string | null): void => {
  if (typeof document === "undefined") return;
  let link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "manifest";
    document.head.appendChild(link);
  }
  const query = tenantSlug ? `?tenant=${encodeURIComponent(tenantSlug)}` : "";
  link.href = `/api/v1/public/manifest.webmanifest${query}`;
};

/** Поставить favicon партнёра вместо стандартного из `index.html`. */
export const applyFavicon = (url: string): void => {
  if (typeof document === "undefined") return;
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.appendChild(link);
  }
  link.href = url;
};
