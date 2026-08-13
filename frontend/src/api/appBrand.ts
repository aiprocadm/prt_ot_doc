import { apiClient } from "@/api/client";

/**
 * Бренд ПРИЛОЖЕНИЯ (ТЗ Доп. №1 разд. 52.2).
 *
 * Отдельный файл от `api/branding.ts` намеренно: тот про бренд ДОКУМЕНТОВ
 * (бланки, реквизиты, печати, подписанты) и живёт на уровне организации.
 * Здесь — имя, цвет и почта самого приложения на уровне арендатора. Сложи их
 * вместе — и «бренд» начнёт означать в коде две разные вещи.
 */
export interface AppBrand {
  app_name: string;
  primary_color: string;
  support_email: string | null;
  /** Откуда бренд: `self` | `reseller` | `platform`. */
  source: string;
  /** Признаки, а не байты: картинки забираются отдельными ручками. */
  has_logo: boolean;
  has_favicon: boolean;
}

export interface TenantBrandingDto {
  app_name: string | null;
  primary_color: string | null;
  support_email: string | null;
  /** СВОИ картинки (не унаследованные): по ним видно, что можно «Убрать». */
  has_logo: boolean;
  has_favicon: boolean;
  effective: AppBrand;
}

/**
 * Действующий бренд арендатора. БЕЗ токена: бренд нужен экрану входа, а на нём
 * токена ещё нет. Отдай его только после входа — и человек увидит сначала
 * вендора, а потом подмену, то есть ровно то, что разд. 52.2 запрещает.
 */
export const getAppBrand = async (): Promise<AppBrand> =>
  (await apiClient.get<AppBrand>("/public/branding")).data;

/**
 * Картинка бренда адресом объекта в памяти страницы.
 *
 * Через API-клиент, а не `<img src>`: тег не умеет передать заголовок
 * арендатора, и сервер не узнал бы, ЧЕЙ логотип отдавать. `null` — картинки
 * нет; это обычное состояние, а не ошибка.
 */
export const getBrandImageUrl = async (
  kind: "logo" | "favicon",
): Promise<string | null> => {
  try {
    const { data } = await apiClient.get<Blob>(`/public/branding/${kind}`, {
      responseType: "blob",
    });
    return URL.createObjectURL(data);
  } catch {
    return null;
  }
};

export const getOwnAppBranding = async (): Promise<TenantBrandingDto> =>
  (await apiClient.get<TenantBrandingDto>("/platform/branding")).data;

export const saveOwnAppBranding = async (payload: {
  app_name: string | null;
  primary_color: string | null;
  support_email: string | null;
}): Promise<TenantBrandingDto> =>
  (await apiClient.put<TenantBrandingDto>("/platform/branding", payload)).data;

/**
 * Загрузить логотип или значок вкладки.
 *
 * Файл уходит формой, а не JSON-строкой: картинка в base64 раздувается на треть,
 * и её пришлось бы держать в памяти целиком с обеих сторон. Тип содержимого
 * заголовком не проставляем — браузер сам добавит границу частей формы, без неё
 * сервер не разберёт тело.
 */
export const uploadOwnBrandImage = async (
  kind: "logo" | "favicon",
  file: File,
): Promise<void> => {
  const body = new FormData();
  body.append("file", file);
  await apiClient.put(`/platform/branding/${kind}`, body);
};

/** Убрать свою картинку — наследование вернётся само. */
export const deleteOwnBrandImage = async (kind: "logo" | "favicon"): Promise<void> => {
  await apiClient.delete(`/platform/branding/${kind}`);
};
