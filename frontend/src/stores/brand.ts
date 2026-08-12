import { createWithEqualityFn } from "zustand/traditional";

import { getAppBrand, type AppBrand } from "@/api/appBrand";

/**
 * Бренд приложения (BIZ-52 срез-4, ТЗ Доп. №1 разд. 52.2).
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
};

interface BrandState {
  brand: AppBrand;
  loaded: boolean;
  loading: boolean;
  load: () => Promise<void>;
  reset: () => void;
}

const initial = {
  brand: PLATFORM_FALLBACK,
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
    } catch {
      // Не закрываемся при ошибке: приложение под платформенным брендом
      // работоспособно, а пустая шапка — нет. Ошибку уже показал общий
      // перехватчик запросов.
      set({ loaded: true, loading: false });
    }
  },
  reset: () => set({ ...initial }),
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
